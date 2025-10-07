# Unreal Asset Utilities

[![ArtStation - krzyzuj](https://img.shields.io/badge/ArtStation-krzyzuj-blue?logo=artstation)](https://artstation.com/krzyzuj)

A collection of Python tools for Unreal Engine that automate the asset pipeline.
Each module registers its scripts under the appropriate menu category, as specified in each module’s README section.

## Requirements
Requires [Pillow](https://pillow.readthedocs.io/en/stable/index.html) 11.3 installed in Unreal Engine's Python environment to run.
[Optionally] [OpenEXR](https://openexr.com/en/latest/python.html) 3.4.0 and [Numpy](https://numpy.org/) 2.3.3 are required for processing the .exr files.

## Installation
Install Pillow via pip for Unreal Engine's Python Environment.
Unreal Engine > Project Settings > Plugins - Python > Additional Paths > path to AssetUtilities folder > Restart Editor
Configure your settings in config_TextureUtilities.json.
Launch the scripts from their registered menus in the editor.

Optional:
Install OpenEXR and Numpy for Unreal Engine's Python Environment for processing the .exr files.

&NewLine;
&NewLine;
# Channel Packer

Gathers the required maps, validates them, and packs channels according to your presets, significantly speeding up the workflow.
More packing modes can be added in config if necessary.
Registers under the Texture2D and folder context menus.

supported map types:  
AO, Roughness, Metalness, Height, Mask, Translucency
Specular, Normal, BentNormal, Bump, Albedo, SSS, Emissive, Glossiness
Config sections: Global, Generators, Channel Packer

texture compression settings types:  
Default, Normalmap, Masks, Grayscale, Displacementmap

To add more map types, add their name, suffixes, and default values to TEXTURE_CONFIG in settings.py.

> Note: Originally a single module with a shared backend for both the standalone version and Unreal Engine.
It was later split for ease of use, but the core structure remains the same, so changes are drop-in across versions.

## Features
- Multiple packing modes defined in the config let you generate various texture combinations in a single pass.
- Supports .exr files and 16bit grayscale (Requires OpenExr and Numpy).
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
|                | no        | unreal_temp_folder  | folder path       | destination folder for exporting source textures for channel packing                    | /Game/TempFolder  |
|                | no        | dest_folder_name    | folder name       | saves generated textures into this subfolder [Content Browser]                          | -                 |
|                | no        | backup_folder_name  | folder name       | moves used files into this subfolder after packing [Content Browser]                    | -                 |
|                | no        | exr_srgb_curve      | true/false        | applies sRGB gamma curve when converting float texture2D, mimicking Photoshop behaviour | true              |
|                | no        | delete_used         | true/false        | deletes used source files after packing                                                 | false             |
| CHANNEL_PACKER |           |                     |                   |                                                                                         |                   |
|                | yes       | resize_strategy     | up/down           | resolves resolution mismatches within a set, by scaling the textures up or down         | down              |
|                | yes       | mode_name           | mode id           | must not be empty to be considered by the function                                      | x                 |
|                | no        | custom_suffix       | suffix name       | custom suffix for the created textures                                                  | auto              |
|                | no        | texture_compression | setting name      | texture compression preset                                                              | Default           |
|                | no        | sRGB                | true/false        | toggles the sRGB flag in the texture settings                                           | true              |
|                | yes       | channels            | texture map types | textures mapped to each channel of the final generated texture; alpha can be left empty | x                 |

