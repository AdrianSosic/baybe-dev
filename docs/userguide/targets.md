# Targets

Targets play a crucial role as the connection between observables measured in an
experiment and the machine learning core behind BayBE.
In general, it is expected that you create one [`Target`](baybe.targets.base.Target)
object for each of your observables.
The way BayBE treats multiple targets is then controlled via the 
[`Objective`](../../userguide/objectives).

## NumericalTarget
```{admonition} Important
:class: important

The {class}`~baybe.targets.numerical.NumericalTarget` class has been redesigned from the
ground up in version [0.14.0](https://github.com/emdgroup/baybe/releases/),
providing a more concise and significantly **more expressive interface.**

For a temporary transition period, the class constructor offers full backward
compatibility with the previous interface, meaning that it can be called with either the
new or the legacy arguments. However, this comes at the cost of **reduced typing
support**, meaning that you won't get type hints (e.g. for autocompletion or static type
checks) for either of the two types of calls. 

For this reason, we offer two additional constructors available for the duration of the
transition period that offer full typing support, which are useful for code development:
{meth}`~baybe.targets.numerical.NumericalTarget.from_legacy_interface` and
{meth}`~baybe.targets.numerical.NumericalTarget.from_modern_interface`.
```

Whenever you want to optimize a real-valued quantity, the 
{class}`~baybe.targets.numerical.NumericalTarget` class is the right choice.
Optimization with targets of this type follows two basic rules:
1. Targets are transformed as specified by their
   {class}`~baybe.transformations.base.Transformation` (with no transformation
   defined being equivalent to the identity transformation).
2. Whenever an optimization direction is required (i.e., when the context is *not*
   active learning), the transformed targets are assumed to be **maximized**.

This results in a simple yet flexible interface:
```python
from baybe.targets import NumericalTarget
from baybe.transformations import LogarithmicTransformation

target = NumericalTarget(
    name="Yield",
    transformation=LogarithmicTransformation(),  # optional transformation object
)
```

While the second rule may seem restrictive at first, it does not limit the
expressiveness of the resulting models, thanks to the transformation step applied.
In fact, other types of optimization problems (e.g., minimization, matching a
specific set point value, or pursuing any other custom objective) are just maximization
problems in disguise, hidden behind an appropriate target transformation.

For example:
* **Minimization** can be achieved by negating the targets before maximizing the
  resulting numerical values.
* **Matching** a set point value can be implemented by applying a transformation that
  computes the "proximity" to the set point in some way (e.g. in terms of the
  negative absolute difference to it).
* In general, any (potentially nonlinear) **custom objective** can be expressed using a
  transformation that assigns higher values to more desirable outcomes and lower values
  to less desirable outcomes.

Especially the first two cases are so common that we provide convenient ways to create
the corresponding target objects:

### Convenience Construction
Eliminating the need to manually provide the necessary
{class}`~baybe.transformations.base.Transformation` object for simple cases, BayBE
offers several convenience approaches to construct targets for many common situations.
The following is a non-comprehensive overview – for a complete list, please refer to the
[`NumericalTarget` documentation](baybe.targets.numerical.NumericalTarget).
* **Minimization**: Minimization of a target can be achieved by simply passing the
  `minimize=True` argument to the constructor:
  ```python
  target = NumericalTarget(
      name="Sideproduct_Yield",
      transformation=PowerTransformation(exponent=2),  # optional transformation object
      minimize=True,  # yield of the side product is to be minimized
  )
  ```

  ````{admonition} Manual Inversion
  :class: note
  Note that the above is mathematically equivalent to chaining the existing
  transformation with an inversion transformation:
  ```python
  from baybe.transformations import AffineTransformation

  target = NumericalTarget(
      name="Sideproduct_Yield",
      transformation=PowerTransformation(exponent=2) | AffineTransformation(factor=-1),
  )
  ```

  Semantically and implementation-wise, however, the two approaches differ:
  * **Semantic difference:** While the handling everything in one transformation
    produces an equivalent output, splitting the construction cleanly separates the
    different user concerns of
      1. Defining the observable itself (e.g. we observe a side product yield)
      2. Defining how the observable enters the objective (e.g. use quadratic scaling
        because small levels are acceptable but large levels are not) 
      3. Defining the optimization direction (e.g. the transformed quantity is to be 
        minimized)
    
    This separation results in a cleaner user interface that avoids mixing the
    optimization goals with the definition of the involved observables.
  * **Implementation difference:** Reflecting the above-mentioned split, the inversion
    is dynamically added before passing the target to the optimization algorithm in the
    one case, while it becomes an integral part of the target transformation attribute
    in the other case.
  ````

* **Matching a set point**: For common matching transformations, we provide
  convenience constructors with the `match_` prefix (see
  {class}`~baybe.targets.numerical.NumericalTarget` for all options).
  
  For example:
  ```python
  # Absolute transformation
  t_abs = NumericalTarget.match_absolute(name="Yield", match_value=42)

  # Bell-shaped transformation
  t_bell = NumericalTarget.match_bell(name="Yield", match_value=42, sigma=5)

  # Triangular transformation
  t1 = NumericalTarget.match_triangular(name="Yield", match_value=42, width=10)
  t2 = NumericalTarget.match_triangular(name="Yield", match_value=42, cutoffs=(37, 47))
  t3 = NumericalTarget.match_triangular(name="Yield", match_value=42, margins=(5, 5))
  assert t1 == t2 == t3
  ```

* **Normalizing targets**: Sometimes, it is necessary to normalize targets to a the
  interval [0, 1], to [align them on a common scale](#target-normalization). One
  situation where this can be required is when combining the targets using a
  {class}`~baybe.objectives.desirability.DesirabilityObjective`. For this purpose, we
  provide convenience constructors with the `normalize_` prefix (see
  {class}`~baybe.targets.numerical.NumericalTarget` for all options).
  
  For example:
  ```python
  target = NumericalTarget.normalize_ramp(name="Yield", cutoffs=(0, 1), descending=True)
  ```

  You can also create a normalized version of an existing target by calling its
  {meth}`~baybe.targets.numerical.NumericalTarget.normalize` method, provided the target
  already maps to a bounded domain. For brevity and demonstration purposes, we show an
  example using [method chaining](method-chaining): 

  ```python
  target = NumericalTarget(name="Yield").power(2).clamp(max=1).normalize()
  ```

(method-chaining)=
* **Creation from existing targets**: Targets can also be quickly created from existing
  ones by calling certain transformation methods on them (see
  {class}`~baybe.targets.numerical.NumericalTarget` for all options).
  
  For example:
  ```python
  t1 = NumericalTarget("Yield")
  t2 = t1 - 10  # subtract a constant
  t3 = t2 / 5  # divide by a constant
  t4 = t3.abs()  # compute absolute value
  t5 = t4.power(2)  # square the value
  t6 = t5.clamp(max=100)  # clamp to (-inf, 100])
  t7 = t6.normalize()  # normalize to [0, 1]
  ```

## Limitations
```{important}
{class}`~baybe.targets.numerical.NumericalTarget` enables many use cases due to the
real-valued nature of most measurements. However, it can also be used to model
categorical targets if they are ordinal.

**For example:**
If your experimental outcome is a categorical ranking into "bad", "mediocre" and "good",
you could use a {class}`~baybe.targets.numerical.NumericalTarget`
by pre-mapping the categories to the values 1, 2 and 3, respectively.

If your target category is not ordinal, the transformation into a numerical target is
not straightforward, which is a current limitation of BayBE. We are looking into adding
more target options in the future.
```