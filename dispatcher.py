
""" Dispatcher for invoking module functions from Unreal. """

import importlib
import inspect
from typing import Any, Optional

import unreal


DEFAULT_FACTORY_NAME: str = "build_ctx"




def run(target_module: str, func_name: str, inject_ctx: Optional[str] = None, debug: bool = False) -> None:

# Importing the target module and resolving its function:
    try:
        module = importlib.import_module(target_module)
    except ModuleNotFoundError as e:
        unreal.log_error(f"[dispatcher] Module not found: {target_module}")
        return
    fn = getattr(module, func_name)



# Building an optional context:
    ctx: Optional[Any] = None
    try:
        ctx = _build_ctx(inject_ctx, target_module, func_name) if inject_ctx else None
    except SystemExit as e:
        unreal.log_error(f"ERROR: [dispatcher] ctx factory aborted (code={e.code})")
    # Handles an intentional abort from the factory (e.g., by sys.exit).
        return

# Calling the function with an injected context:
    try:
        if ctx is not None:
            try:
                if debug: unreal.log(f"[dispatcher] Calling {target_module}.{func_name} with ctx={type(ctx).__name__}")

                fn(ctx=ctx) # Call with the context.

                if debug: unreal.log(f"[dispatcher] {func_name} finished OK")
                return

            except TypeError as te:
                unreal.log_error(f"[dispatcher] '{func_name}' rejected context (TypeError: {te})")
            return
    # Initially tries with an injected context when available.



# If no context is provided, call the function without injection:
        if debug: unreal.log(f"[dispatcher] calling {target_module}.{func_name} ()")

        fn() # Call without the context.

        if debug: unreal.log(f"[dispatcher] {func_name} finished OK")

    except SystemExit as e:
        if debug: unreal.log_error(f"[{func_name}] aborted (code={e.code})")


def _split_module_and_factory(spec: str):
    # Extracts an explicit factory name if provided as "module:factory"; otherwise leaves it None.
    spec = (spec or "").strip()
    if not spec:
        return "", None
    parts = spec.split(":", 1)
    return parts[0].strip(), (parts[1].strip() if len(parts) == 2 else None)




#                                     === not used right now ===
def _build_ctx(inject_ctx: str, target_module: str, func_name: str, debug: bool = False):
# Tries to locate and call a context factory; returns the built context object or None.


# Importing the context module and determining the factory name:
    mod_name, explicit_factory = _split_module_and_factory(inject_ctx)
    m = importlib.import_module(mod_name)
    factory_name = explicit_factory or DEFAULT_FACTORY_NAME
    factory: str = getattr(m, factory_name, None)



# Invoking the factory function:
    if not callable(factory):
        if debug:
            unreal.log_error(f"[dispatcher: ctx_build] Context '{mod_name}.{factory_name}' not found.")
        return None

    try:
        sig  = inspect.signature(factory)
        params = len(sig.parameters)
    # Gets how many parameters the factory function declares.


# Deriving how many arguments the factory needs:
    except (TypeError, ValueError):
        if debug:
            unreal.log_error("[dispatcher: ctx_build] Cannot extract context factory signature.")
        return None

    if params == 0:
        return factory() # Factory expects no parameters
    elif params == 1:
        return factory(func_name) # Factory expects one parameter: pass func_name to let it select behavior.
    elif params == 2:
        return factory(target_module, func_name) # Factory expects two parameters: pass module and function name.

    if debug:
        unreal.log_error(f"[dispatcher: ctx_build] Context factory unsupported).") # More than 2 parameters are not supported.
    return None