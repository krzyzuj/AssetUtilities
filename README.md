# Unreal Asset Utilities

[![ArtStation - krzyzuj](https://img.shields.io/badge/ArtStation-krzyzuj-blue?logo=artstation)](https://artstation.com/krzyzuj)

A collection of Python tools for Unreal Engine that automate the asset pipeline.
Each module registers its scripts under the appropriate menu category, as specified in each module’s README section.

## Requirements
Requires [Pillow](https://pillow.readthedocs.io/en/stable/index.html) 11.3 installed in Unreal Engine's Python environment to run.

## Installation
Install Pillow via pip for Unreal Engine's Python Environment.
Unreal Engine > Project Settings > Plugins - Python > Additional Paths > path to AssetUtilities folder > Restart Editor
Configure your settings in config_TextureUtilities.json.
Launch the scripts from their registered menus in the editor.

&NewLine;
&NewLine;
# Channel Packer

Gathers the required maps, validates them, and packs channels according to your presets, significantly speeding up the workflow.
Registers under the Texture2D and folder context menus.

Config sections: Global, Generators, Channel Packer

> Note: Originally a single module with a shared backend for both the standalone version and Unreal Engine.
It was later split for ease of use, but the core structure remains the same, so changes are drop-in across versions.

## Features
- Multiple packing modes defined in the config let you generate various texture combinations in a single pass.
- Automatic organization: moves created and/or source maps into subdirectories to keep things tidy.
- Flexible inputs: supports packing grayscale textures as well as extracting specific channels from RGB sources.
- Validation & logging: checks for resolution mismatches, incorrect filenames, and missing maps, and logs any issues it finds.
- Texture settings: applies the specified compression settings and sRGB flag to newly created textures.
- Auto-repair options: can fill missing channels with default values and rescale mismatched textures when needed.

## Config
&NewLine;

| type           | mandatory | label               | input type        | description                                                                             | if empty          |
|----------------|-----------|---------------------|-------------------|-----------------------------------------------------------------------------------------|-------------------|
| GLOBAL         |           |                     |                   |                                                                                         |                   |
|                | no        | auto_save           | true/false        | auto-saves unsaved assets before processing                                             | just logs unsaved |
|                | no        | show_details        | true/false        | shows additional info in logs                                                           | false             |
| GENERATORS     |           |                     |                   |                                                                                         |                   |
|                | yes       | file_type           | file ext          | file type extension for the created texture files                                       | png               |
|                | no        | unreal_temp_folder  | folder path       | destination folder for exporting source textures for channel packing                    | /Game/TempFolder  |
|                | no        | dest_folder_name    | folder name       | saves generated textures into this subfolder [Content Browser]                          | -                 |
|                | no        | backup_folder_name  | folder name       | moves used files into this subfolder after packing [Content Browser]                    | -                 |
|                | no        | delete_used         | true/false        | deletes used source files after packing                                                 | false             |
| CHANNEL_PACKER |           |                     |                   |                                                                                         |                   |
|                | yes       | resize_strategy     | up/down           | resolves resolution mismatches within a set, by scaling the textures up or down         | down              |
|                | yes       | mode_name           | mode id           | must not be empty to be considered by the function                                      | x                 |
|                | no        | custom_suffix       | suffix name       | custom suffix for the created textures                                                  | auto              |
|                | no        | texture_compression | setting name      | texture compression preset                                                              | Default           |
|                | no        | sRGB                | true/false        | toggles the sRGB flag in the texture settings                                           | true              |
|                | yes       | channels            | texture map types | textures mapped to each channel of the final generated texture; alpha can be left empty | x                 |

&NewLine;
supported map types:

AO, Roughness, Metalness, Height, Mask, Translucency
Specular, Normal, Albedo, SSS, Emissive, Glossiness
