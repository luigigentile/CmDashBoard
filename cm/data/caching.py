from inspect import signature
from typing import Any, Callable, List, TypeVar, cast

from cacheops import cached_as
from django.db.models import Model, QuerySet

F = TypeVar("F", bound=Callable[..., Any])


def cached(
    *dependencies: Any, callback: Callable[..., List[Any]] = None, timeout: int = None
) -> Callable[[F], F]:
    def wrapper(f: F) -> F:
        def wrapped(*args: Any, **kwargs: Any):  # type: ignore

            processed_dependencies = []
            f_signature = signature(f)
            for raw_dependency in dependencies:
                # Dependencies can be models, querysets or instances
                # We also allow passing in a dependency as a string, which signals that this dependency
                # should be taken from the arguments to f.
                if isinstance(raw_dependency, str):
                    # Find the dependency in f's positional or keyword parameters.
                    # Try the keyword arguments first
                    if raw_dependency in kwargs:
                        processed_dependency = kwargs[raw_dependency]
                    else:
                        # This is a positional argument, so we have to extract the item of args with the fitting index.
                        for arg_index, arg_name in list(
                            enumerate(f_signature.parameters)
                        )[: len(args)]:
                            if arg_name == raw_dependency:
                                processed_dependency = args[arg_index]
                                break
                        else:
                            # If it wasn't passed as a positional parameter, use the default value (if any)
                            processed_dependency = f_signature.parameters[
                                raw_dependency
                            ].default
                else:
                    processed_dependency = raw_dependency

                # Skip any None values
                if processed_dependency is None:
                    continue

                # Validate that the processed dependency is a valid type for caching
                is_instance_or_queryset = isinstance(
                    processed_dependency, (Model, QuerySet)
                )
                is_model = isinstance(processed_dependency, type) and issubclass(
                    processed_dependency, Model
                )
                is_valid = is_instance_or_queryset or is_model
                if is_valid:
                    # If the dependency is an instance, model or queryset, all is well
                    processed_dependencies.append(processed_dependency)
                else:
                    raise RuntimeError(
                        f"Programming error, {processed_dependency} is not a model, instance, or queryset!"
                    )

            if callback:
                # We allow callbacks to return none values as that's a common case for related objects.
                # But we do have to filter them out here, because cacheops doesn't like receiving none values
                processed_dependencies = [
                    dep for dep in callback(*processed_dependencies) if dep is not None
                ]

            return cached_as(*processed_dependencies, timeout=timeout)(f)(
                *args, **kwargs
            )

        return cast(F, wrapped)

    return wrapper
