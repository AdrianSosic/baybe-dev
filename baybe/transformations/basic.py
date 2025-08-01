"""Basic transformations."""

from __future__ import annotations

import gc
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
from attrs import Factory, define, field
from attrs.validators import ge, gt, instance_of, is_callable
from typing_extensions import override

from baybe.serialization.core import (
    converter,
    get_base_structure_hook,
    unstructure_base,
)
from baybe.transformations.base import MonotonicTransformation, Transformation
from baybe.utils.dataframe import to_tensor
from baybe.utils.interval import Interval
from baybe.utils.validation import finite_float

if TYPE_CHECKING:
    from torch import Tensor

    from baybe.targets.botorch import AffinePosteriorTransform

    TensorCallable = Callable[[Tensor], Tensor]
    """Type alias for a torch-based function mapping from reals to reals."""


@define
class CustomTransformation(Transformation):
    """A custom transformation applying an arbitrary torch callable."""

    function: TensorCallable = field(validator=is_callable())
    """The torch callable representing the transformation."""

    @override
    def get_image(self, interval: Interval | None = None, /) -> Interval:
        raise NotImplementedError(
            "Custom transformations do not provide details about their image."
        )

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return self.function(x)


@define
class IdentityTransformation(MonotonicTransformation):
    """The identity transformation."""

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return x

    @override
    def __add__(self, other: Transformation | int | float) -> Transformation:
        if isinstance(other, (int, float)):
            return AffineTransformation(shift=other)
        return other


@define(init=False)
class ClampingTransformation(MonotonicTransformation):
    """A transformation clamping values between specified bounds."""

    bounds: Interval = field(converter=Interval.create)  # type: ignore[misc]
    """The range to which input values are clamped."""

    def __init__(self, min: float | None = None, max: float | None = None) -> None:
        if min is None and max is None:
            raise ValueError("At least one bound must be specified.")
        self.__attrs_init__(bounds=Interval(min, max))

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return x.clamp(*self.bounds.to_tuple())


@define(slots=False, init=False)
class AffineTransformation(MonotonicTransformation):
    """An affine transformation."""

    factor: float = field(default=1.0, converter=float, validator=finite_float)
    """The multiplicative factor of the transformation."""

    shift: float = field(default=0.0, converter=float, validator=finite_float)
    """The constant shift of the transformation."""

    def __init__(
        self,
        factor: float = 1.0,
        shift: float = 0.0,
        *,
        shift_first: bool = False,
    ) -> None:
        if shift_first:
            shift = shift * factor
            if not np.isfinite(shift):
                raise OverflowError("The transformation produces infinite values.")
        self.__attrs_init__(factor=factor, shift=shift)

    @override
    def __eq__(self, other: Any, /) -> bool:
        # An affine transformation without shift and scaling is effectively an
        # identity transformation
        if (
            isinstance(other, IdentityTransformation)
            and self.factor == 1.0
            and self.shift == 0.0
        ):
            return True

        # TODO: https://github.com/python-attrs/attrs/issues/1452
        return (
            super().__eq__(other)
            and isinstance(other, AffineTransformation)
            and self.factor == other.factor
            and self.shift == other.shift
        )

    def to_botorch_posterior_transform(self) -> AffinePosteriorTransform:
        """Convert to BoTorch posterior transform.

        Returns:
            The representation of the transform as BoTorch posterior transform.
        """
        from baybe.targets.botorch import AffinePosteriorTransform

        return AffinePosteriorTransform(self.factor, self.shift)

    @classmethod
    def from_points_mapped_to_unit_interval_bounds(
        cls, mapped_to_zero: float, mapped_to_one: float
    ) -> AffineTransformation:
        """Create an affine transform by specifying reference points mapped to 0/1.

        Args:
            mapped_to_zero: The input value that will be mapped to zero.
            mapped_to_one: The input value that will be mapped to one.

        Returns:
            An affine transformation calibrated to map the specified values to the
            unit interval.

        Example:
            >>> import torch
            >>> from baybe.transformations import AffineTransformation as AffineT
            >>> transform = AffineT.from_points_mapped_to_unit_interval_bounds(3, 7)
            >>> transform(torch.tensor([3, 7]))
            tensor([0., 1.])
            >>> transform(torch.tensor([7, 3]))
            tensor([1., 0.])
        """
        return AffineTransformation(
            shift=-mapped_to_zero,
            factor=1 / (mapped_to_one - mapped_to_zero),
            shift_first=True,
        )

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        # Handle problematic case where input contains infinity (to avoid 0 * inf)
        if self.factor == 0.0:
            return x.new_full(x.shape, fill_value=self.shift)

        return x * self.factor + self.shift


@define(slots=False)
class TwoSidedAffineTransformation(Transformation):
    """A transformation with two affine segments on either side of a midpoint."""

    slope_left: float = field(converter=float, validator=finite_float)
    """The slope of the affine segment to the left of the midpoint."""

    slope_right: float = field(converter=float, validator=finite_float)
    """The slope of the affine segment to the right of the midpoint."""

    midpoint: float = field(default=0.0, converter=float, validator=finite_float)
    """The midpoint where the two affine segments meet."""

    @override
    def get_image(self, interval: Interval | None = None, /) -> Interval:
        interval = Interval.create(interval)

        image_lower = self(to_tensor(interval.lower)).item()
        image_upper = self(to_tensor(interval.upper)).item()
        min_val, max_val = sorted([image_lower, image_upper])
        if interval.contains(self.midpoint):
            return Interval(min(0, min_val), max(0, max_val))
        else:
            return Interval(min_val, max_val)

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        import torch

        # Note: the if conditions handle the problematic cases where input contains
        #  infinity (to avoid 0 * inf)
        mid = self.midpoint
        return torch.where(
            x < mid,
            (x - mid) * sl if (sl := self.slope_left) else x.new_zeros(x.shape),
            (x - mid) * sr if (sr := self.slope_right) else x.new_zeros(x.shape),
        )


@define(slots=False)
class BellTransformation(Transformation):
    """A Gaussian bell curve transformation."""

    center: float = field(default=0.0, converter=float, validator=finite_float)
    """The center point of the bell curve."""

    sigma: float = field(
        default=1.0, converter=float, validator=[finite_float, gt(0.0)]
    )
    """The scale parameter of the transformation.

    Concerning the width of the bell curve, it has the same interpretation as the
    standard deviation in a Gaussian distribution. (The magnitude of the curve is
    not affected and always reaches a maximum value of 1 at the center.)
    """

    @override
    def get_image(self, interval: Interval | None = None, /) -> Interval:
        interval = Interval.create(interval)

        image_lower = self(to_tensor(interval.lower)).item()
        image_upper = self(to_tensor(interval.upper)).item()
        if interval.contains(self.center):
            return Interval(min(image_lower, image_upper), 1)
        else:
            return Interval(*sorted([image_lower, image_upper]))

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return x.sub(self.center).div(self.sigma).pow(2.0).div(2.0).neg().exp()


@define(slots=False)
class AbsoluteTransformation(Transformation):
    """A transformation computing absolute values."""

    _transformation: Transformation = field(
        factory=lambda: TwoSidedAffineTransformation(slope_left=-1, slope_right=1),
        init=False,
        repr=False,
    )
    """Internal transformation object handling the operations."""

    @override
    def get_image(self, interval: Interval | None = None, /) -> Interval:
        return self._transformation.get_image(interval)

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return self._transformation(x)


@define(slots=False)
class TriangularTransformation(Transformation):
    r"""A transformation with a triangular shape.

    The transformation is defined by a peak location between two cutoff values. Outside
    the region delimited by the cutoff values, the transformation is zero. Inside the
    region, the transformed values increase linearly from both cutoffs to the peak,
    where the highest value of 1 is reached:

    .. math::
        f(x) =
        \begin{cases}
            0 & \text{if } x < c_1 \\
            \frac{x - c_1}{p - c_1} & \text{if } c_1 \leq x < p \\
            \frac{c_2 - x}{c_2 - p} & \text{if } p \leq x < c_2 \\
            0 & \text{if } c_2 \leq x
        \end{cases}

    where :math:`c_1` and :math:`c_2` are the left and right cutoffs, respectively, and
    :math:`p` is the peak location, with :math:`c_1 < p < c_2`.
    """

    # TODO[typing]: https://github.com/python-attrs/attrs/issues/1435
    cutoffs: Interval = field(converter=Interval.create)  # type: ignore[misc]
    """The cutoff values where the transformation reaches zero."""

    peak: float = field(
        default=Factory(lambda self: self.cutoffs.center, takes_self=True),
        converter=float,
    )
    """The peak location of the transformation. By default, centered between cutoffs."""

    _transformation: Transformation = field(init=False, repr=False)
    """Internal transformation object handling the operations."""

    def __attrs_post_init__(self) -> None:
        # We use post-init here to ensure the attribute validators run first,
        # since otherwise the validators of the transformation object created here
        # would be executed first, raising difficult-to-interpret errors

        slope_left = 1 / self.margins[0]
        slope_right = -1 / self.margins[1]
        if np.isinf([slope_left, slope_right]).any():
            raise OverflowError(
                "The triangular transformation could not be initialized because "
                "the cutoffs are too close to the peak, leading to numerical overflow "
                "when computing the slopes."
            )
        self._transformation = (
            TwoSidedAffineTransformation(
                slope_left=1 / self.margins[0],
                slope_right=-1 / self.margins[1],
                midpoint=self.peak,
            )
            + 1
        ).clamp(min=0)

    @cutoffs.validator
    def _validate_cutoffs(self, _, cutoffs: Interval) -> None:
        if not cutoffs.is_bounded:
            raise ValueError(
                "The cutoffs of the transformation must be bounded. "
                f"Given cutoffs: {cutoffs.to_tuple()}."
            )

    @peak.validator
    def _validate_peak(self, _, peak: float) -> None:
        if not (self.cutoffs.lower < peak < self.cutoffs.upper):
            raise ValueError(
                f"The peak of the transformation must be located strictly between the "
                f"specified cutoff values. Given peak location: {peak}. "
                f"Given cutoffs: {self.cutoffs.to_tuple()}."
            )

    @property
    def margins(self) -> tuple[float, float]:
        """The left and right margin denoting the width of the triangle."""
        return self.peak - self.cutoffs.lower, self.cutoffs.upper - self.peak

    @classmethod
    def from_margins(
        cls, peak: float, margins: Sequence[float]
    ) -> TriangularTransformation:
        """Create a triangular transformation from a peak location and margins."""
        if len(margins) != 2:
            raise ValueError(
                "The margins must be provided as a sequence of two values."
            )
        return cls(peak=peak, cutoffs=Interval(peak - margins[0], peak + margins[1]))

    @classmethod
    def from_width(cls, peak: float, width: float) -> TriangularTransformation:
        """Create a triangular transformation from a peak location and width."""
        return cls.from_margins(peak, (width / 2, width / 2))

    @override
    def get_image(self, interval: Interval | None = None, /) -> Interval:
        return self._transformation.get_image(interval)

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return self._transformation(x)


@define(frozen=True)
class LogarithmicTransformation(MonotonicTransformation):
    """A logarithmic transformation."""

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return x.log()


@define(frozen=True)
class ExponentialTransformation(MonotonicTransformation):
    """An exponential transformation."""

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return x.exp()


@define(slots=False)
class PowerTransformation(Transformation):
    """A transformation computing the power."""

    # TODO: Could be generalized to floats but then requires runtime checks on the input
    #   tensor exponents to avoid producing complex numbers and adjusting the image
    #   computation logic
    exponent: int = field(validator=[instance_of(int), ge(2)])
    """The exponent of the power transformation."""

    @override
    def get_image(self, interval: Interval | None = None, /) -> Interval:
        interval = Interval.create(interval)
        image_lower = self(to_tensor(interval.lower)).item()
        image_upper = self(to_tensor(interval.upper)).item()
        if self.exponent % 2 == 0 and interval.contains(0.0):
            return Interval(0, max(image_lower, image_upper))
        else:
            return Interval(*sorted([image_lower, image_upper]))

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        return x.pow(self.exponent)


@define(slots=False)
class SigmoidTransformation(MonotonicTransformation):
    """A sigmoid transformation."""

    center: float = field(default=0.0, converter=float)
    """The center of the sigmoid function, where it crosses 0.5."""

    steepness: float = field(default=1.0, converter=float)
    """The steepness of the sigmoid function."""

    @classmethod
    def from_anchors(cls, anchors: Sequence[Sequence[float]]) -> SigmoidTransformation:
        """Create a sigmoid transformation from two anchor points.

        Args:
            anchors: The anchor points defining the sigmoid transformation.
                Must be convertible to two pairs of floats, where each pair represents
                an anchor point through which the sigmoid curve passes.

        Raises:
            ValueError: If the input given as anchors does not represent two points.
            ValueError: If the ordinates of the anchors are not in the unit interval.

        Returns:
            A sigmoid transformation passing through the specified anchor points.

        Example:
            >>> import torch
            >>> p1 = (-2, 0.1)
            >>> p2 = (5, 0.6)
            >>> t = SigmoidTransformation.from_anchors([p1, p2])
            >>> out = t(torch.tensor([p1[0], p2[0]]))
            >>> assert torch.equal(out, torch.tensor([p1[1], p2[1]]))
        """
        import cattrs

        # Extract point coordinates from the input
        try:
            anchors = cattrs.structure(
                anchors, tuple[tuple[float, float], tuple[float, float]]
            )  # type: ignore[call-arg]
        except cattrs.IterableValidationError as ex:
            raise ValueError(
                f"The specified anchor point argument must be convertible to two "
                f"pairs of floats. Given: {anchors}"
            ) from ex
        (x1, y1), (x2, y2) = anchors

        if not ((0.0 < y1 < 1.0) and (0.0 < y2 < 1.0)):
            raise ValueError(
                f"The ordinates of the anchor points must be in the open "
                f"interval (0, 1). Given: {y1=} and {y2=}."
            )

        k1 = np.log(1 / y1 - 1)
        k2 = np.log(1 / y2 - 1)
        shift = (k2 * x1 - k1 * x2) / (k2 - k1)
        steepness = (k2 - k1) / (x2 - x1)
        return SigmoidTransformation(shift, steepness)

    @override
    def __call__(self, x: Tensor, /) -> Tensor:
        import torch

        return 1 / (1 + torch.exp(self.steepness * (x - self.center)))


# Register (un-)structure hooks
converter.register_structure_hook(
    Transformation, get_base_structure_hook(Transformation)
)
converter.register_unstructure_hook(Transformation, unstructure_base)

# Collect leftover original slotted classes processed by `attrs.define`
gc.collect()
