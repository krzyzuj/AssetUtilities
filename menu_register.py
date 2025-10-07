
""" Unreal menu integration — registers Python actions in Editor menus and optional submenus. """

import re
from typing import TypedDict, NotRequired, Tuple, Optional

import unreal


class MenuEntry(TypedDict, total=False):
    label: NotRequired[str] # Falls back to the function name if missing.
    target_module: str # Full dotted path to the Python module, or ".module:func".
    inject_ctx: NotRequired[str] # Optional; Full dotted path to the external context factory module or ".module:factory". Default looks for a factory name: build_ctx.
    tooltip: NotRequired[str] # Optional tooltip
    section_name: NotRequired[str] # Optional; internal section name for grouping menu items, e.g., GetAssetActions (TEXTURE ACTIONS). Automatically derives label from the name.
    also_in_folders: NotRequired[bool] # Optional: Makes the menu show up also in the folder's contex menu.
    icon: NotRequired[str] # Generic AppStyle key (e.g. "ClassIcon.Texture2D", "ClassThumbnail.Texture2D", "Icons.Save").




#                                       === main registering function ===

# Default Menu:
SECTION_NAME_DEFAULT  = "AssetUtilities"

def menu_register(
    menu: str,
    entries: list[MenuEntry],
    debug: bool = False,
    submenu: Optional[str] = None,  # Optional submenu name under which all entries are grouped.
) -> bool:


# Pre-validation:
    available_menus = unreal.ToolMenus.get()
    menus = unreal.ToolMenus.get()
    menu_target = menus.find_menu(menu)
    if not menu_target and debug:
        unreal.log_warning(f"[menu_register] Target menu '{menu}' not available yet. Skipping registration.")
        return False
    # Checks if a specified menu exists

    folder_menu = available_menus.extend_menu("ContentBrowser.FolderContextMenu")

    if not entries:
        unreal.log_warning(f"[menu_register] No entries for {menu}.")
        return False


# Setting up a section name and (optionally) label from the first entry:
    if "section_name" in entries[0]:
        section_name = entries[0].get("section_name") or SECTION_NAME_DEFAULT
    else:
        section_name = SECTION_NAME_DEFAULT

    if not _section_exist(menu_target, section_name):
        section_label = _name_to_label(section_name)  # Derives label from the name.
        menu_target.add_section(section_name, section_label)
    # Ensures the target section exists. Creates a new one if needed.


# (Optionally) creating a submenu for all the entries:
    if submenu:
        submenu_name = _label_to_name(submenu)
        submenu_target = _add_submenu(menu_target, section_name, section_label, submenu_name, submenu)
        target_menu_for_entries = submenu_target
    else:
        target_menu_for_entries = menu_target


# Registering each entry:
    entries_added: int = 0 # Counts how many entries were registered.
    clones_added: int = 0 # Counts how many cloned entries were registered to the folder context menu.

    for item in entries:
        target_module = (item.get("target_module") or "").strip()
        module_path, function_name = _split_target_module_name(target_module)
        if not module_path or not function_name:
            unreal.log_error("[menu_register] Skipping entry: invalid target_module.")
            continue
        # Validates the target_module specification.

        label = item.get("label", function_name)
        inject_ctx = item.get("inject_ctx", "")

        cmd = (
            "import importlib; from AssetUtilities import dispatcher as _d; importlib.reload(_d); "
            f"_d.run({module_path!r}, {function_name!r}, inject_ctx={inject_ctx!r}, debug={debug!r})"
        )
        # Command executed by the Unreal, using the dispatcher, when the menu entry is clicked.

        entry = unreal.ToolMenuEntry(
            name = function_name,
            type = unreal.MultiBlockType.MENU_ENTRY,
            insert_position = unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT)

        )
        entry.set_label(label)
        # Adds the button to the menu.

        tooltip_text = item.get("tooltip", "")
        if tooltip_text:
            entry.set_tool_tip(tooltip_text)
        # Adds a tooltip if specified.

        entry.set_string_command(
            type = unreal.ToolMenuStringCommandType.PYTHON,
            custom_type = "",
            string = cmd,
        )

        _apply_icon(entry, item, debug) # (Optionally) creates an icon for the menu.

        target_menu_for_entries.add_menu_entry(section_name, entry)
        # Attaches the command to the created button.
        entries_added += 1


# (Optionally) registering a clone of each entry to the folder context menu too:

        if item.get("also_in_folders"):
            folder_menu.add_section(section_name, section_label)

            folder_target = folder_menu
            if submenu:
                folder_target = _add_submenu(folder_menu, section_name, section_label, submenu_name, submenu)
            # Creates a subfolder for all entries if one is already created for "regular" entries.

            clone = unreal.ToolMenuEntry(
                name = function_name,
                type = unreal.MultiBlockType.MENU_ENTRY,
                insert_position = unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT)
            )
            clone.set_label(label)
            # Adds the button to the menu.

            if tooltip_text:
                clone.set_tool_tip(tooltip_text)
            # Adds a tooltip if specified.

            clone.set_string_command(
                type = unreal.ToolMenuStringCommandType.PYTHON,
                custom_type = "",
                string = cmd,
            )

            _apply_icon(clone, item, debug) # (Optionally) creates an icon for the menu.

            folder_target.add_menu_entry(section_name, clone)
            # Attaches the command to the created button.
            clones_added += 1
        # Allows the button to be displayed from the folder's context menu too.




# Refreshing the UI:
    try:
        path: str = f"{menu}.{submenu_name}" if (submenu and submenu_name) else menu
        available_menus.refresh_menu_widget(path)
    except RuntimeError:
        available_menus.refresh_all_widgets()
    # Tries a targeted refresh; if that widget isn't available, fall back to a full UI refresh.




# Logs:
    where: str = f"{menu}{(' > ' + submenu) if submenu else ''}"
    if entries_added == 1:
        unreal.log(f"[menu_register] Registered 1 entry at: {where}")
    else:
        unreal.log(f"[menu_register] Registered {entries_added} entries at: {where}")
    if clones_added:
        folder_where: str = f"Folder Context menu{(' > ' + submenu) if submenu else ''}"
        if entries_added == 1:
            unreal.log(f"[menu_register] Cloned {clones_added} entry to: {folder_where}")
        else:
            unreal.log(f"[menu_register] Cloned {clones_added} entries at: {folder_where}")

    return True




#                                       === helpers ===

def _add_submenu(parent_menu: unreal.ToolMenu, section_name: str, section_label: str, submenu_id: str, submenu_label: str) -> unreal.ToolMenu:
# Ensures the submenu exists (creates if missing) and returns it.

    sub = parent_menu.add_sub_menu("AssetUtilities", section_name, submenu_id, submenu_label, "")
    sub.add_section(section_name, section_label)
    return sub


def _apply_icon(entry: unreal.ToolMenuEntry, item: MenuEntry, debug: bool = False) -> None:
# Applies an icon based on a general icon key. Defaults to the Editor Style icons.
# But if a given icon doesn't appear because it's from the App Style, it can be switched to the App Style by typing: "AppStyle:icon".


    spec = (item.get("icon") or "").strip()
    if not spec:
        return

    default_style_set: str = "EditorStyle"

# Checking if the icon style is specified:
    if ":" in spec:
        style_set_raw, brush_raw = spec.split(":", 1)
        style_set = style_set_raw.strip()
        brush = brush_raw.strip()
    else:
        style_set = default_style_set
        brush = spec
    # If not specified, defaults to the Editor Style.

    if not brush and debug:
        unreal.log_warning(f"[menu_register][icon] Empty brush after parsing spec='{spec}'")
        return


# Creating a big and small icon pair needed by the UE class:
    if brush.startswith(("ClassIcon.", "ClassThumbnail.")): # e.g., ClassIcon.Texture2D
        class_   = brush.split(".", 1)[1]
        big   = f"ClassThumbnail.{class_}"
        small = f"ClassIcon.{class_}"
    else:
        big = small = brush  # e.g., "Icons.Save"


    entry.set_icon(style_set, style_name=big, small_style_name=small)

    if debug:
        unreal.log(f"[menu_register][icon] applied style='{style_set}' big='{big}' small='{small}'")


def _label_to_name(label: str) -> str:
    # Derives submenu name from it
    s = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return s or "SubMenu"


def _name_to_label(name: str) -> str:
# Derives the menu label from its name.
# E.g., PythonTextureTools -> Python Texture Tools

    name = (name or "").strip()
    if not name:
        return ""

    name = re.sub(r"(?<!^)(?=[A-Z])", " ", name) # Adds whitespaces before each capital letter but the first one.
    name = re.sub(r"\s+", " ", name).strip() # In case - deletes multiple whitespaces.
    return name


def _section_exist(menu: unreal.ToolMenu, name: str) -> bool:
# Checks if the menu already contains a section with the given name.

    try:
        secs = menu.get_sections()
        return any(s.name == name for s in secs)
    except Exception:
        return False


def _split_target_module_name(module_path: str) -> Tuple[str, str]:
# Allows the function name to be specified in the target_module path, or not.
# If not, derives the function name from the module name.


    s = (module_path or "").strip()
    if not s:
        return "", ""
    if ":" in s:
        mod, func = s.split(":", 1)
        mod = mod.strip()
        func = func.strip()
        return (mod, func) if mod and func else ("", "")


    if "." not in s:
        return "", ""
    # Check to ensure a dotted path is provided.

    return s, s.rsplit(".", 1)[-1]
    # If no function name is specified in the path, derive it from the module name.