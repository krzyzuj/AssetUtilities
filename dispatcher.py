
""" Dispatcher for invoking module functions from Unreal. """

import importlib
import inspect
from typing import Any, Optional

import unreal


DEFAULT_FACTORY_NAME: str = "build_build_context"




def run(target_module: str, function_name: str, inject_context: Optional[str] = None, debug: bool = False) -> None:

# Importing the target module and resolving its function:
    try:
        module = importlib.import_module(target_module)
    except ModuleNotFoundError as e:
        unreal.log_error(f"[dispatcher] Module not found: {target_module}")
        return
    function = getattr(module, function_name)



# Building an optional context:
    context: Optional[Any] = None
    try:
        context = _build_context(inject_context, target_module, function_name) if inject_context else None
    except SystemExit as e:
        unreal.log_error(f"ERROR: [dispatcher] context factory aborted (code={e.code})")
    # Handles an intentional abort from the factory (e.g., by sys.exit).
        return

# Calling the function with an injected context:
    try:
        if context is not None:
            try:
                if debug: unreal.log(f"[dispatcher] Calling {target_module}.{function_name} with context = {type(context).__name__}")

                function(build_context = context) # Call with the context.

                if debug: unreal.log(f"[dispatcher] {function_name} finished OK")
                return

            except TypeError as te:
                unreal.log_error(f"[dispatcher] '{function_name}' rejected context (TypeError: {te})")
            return
    # Initially tries with an injected context when available.



# If no context is provided, call the function without injection:
        if debug: unreal.log(f"[dispatcher] calling {target_module}.{function_name} ()")

        function() # Call without the context.

        if debug: unreal.log(f"[dispatcher] {function_name} finished OK")

    except SystemExit as e:
        if debug: unreal.log_error(f"[{function_name}] aborted (code={e.code})")


def _split_module_and_factory(specified: str):
    # Extracts an explicit factory name if provided as "module:factory"; otherwise leaves it None.
    specified = (specified or "").strip()
    if not specified:
        return "", None
    parts = specified.split(":", 1)
    return parts[0].strip(), (parts[1].strip() if len(parts) == 2 else None)




#                                     === not used right now ===
def _build_context(inject_context: str, target_module: str, func_name: str, debug: bool = False):
# Tries to locate and call a context factory; returns the built context object or None.


# Importing the context module and determining the factory name:
    mod_name, explicit_factory = _split_module_and_factory(inject_context)
    module = importlib.import_module(mod_name)
    factory_name = explicit_factory or DEFAULT_FACTORY_NAME
    factory: str = getattr(module, factory_name, None)



# Invoking the factory function:
    if not callable(factory):
        if debug:
            unreal.log_error(f"[dispatcher: build_context] Context '{mod_name}.{factory_name}' not found.")
        return None

    try:
        signature  = inspect.signature(factory)
        params = len(signature.parameters)
    # Gets how many parameters the factory function declares.


# Deriving how many arguments the factory needs:
    except (TypeError, ValueError):
        if debug:
            unreal.log_error("[dispatcher: build_context] Cannot extract context factory signature.")
        return None

    if params == 0:
        return factory() # Factory expects no parameters
    elif params == 1:
        return factory(func_name) # Factory expects one parameter: pass func_name to let it select behavior.
    elif params == 2:
        return factory(target_module, func_name) # Factory expects two parameters: pass module and function name.

    if debug:
        unreal.log_error(f"[dispatcher: build_context] Context factory unsupported).") # More than 2 parameters are not supported.
    return None