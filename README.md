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


# Channel Packer

Gathers the required maps, validates them, and packs channels according to your presets, significantly speeding up the workflow.
More packing modes can be added in config if necessary.
Registers under the Texture2D and folder context menus.

## Features
- Multiple packing modes defined in the config let you generate various texture combinations in a single pass.
- Supports .exr files and 16bit grayscale (Requires OpenExr and Numpy).
- Automatic organization: moves created and/or source maps into subdirectories to keep things tidy.
- Flexible inputs: supports packing grayscale textures as well as extracting specific channels from RGB sources.
- Validation & logging: checks for resolution mismatches, incorrect filenames, and missing maps, and logs any issues it finds.
- Texture settings: applies the specified compression settings and sRGB flag to newly created textures.
- Auto-repair options: can fill missing channels with default values and rescale mismatched textures when needed.

> Note: Originally a single module with a shared backend for both the standalone version and Unreal Engine.
It was later split for ease of use, but the core structure remains the same, so changes are drop-in across versions.

# Linear Color Curve Sampler

Creates curves with colors sampled from selected textures. Ready to use in a shader setup without manual hue setting.
Includes multiple lightness partition methods and hue-selection priorities for flexible control.

## Features
- Flexible sampling: perceptual and uniform (even) image lightness partitioning to prioritize different value ranges.
- Hue priority presets: dominant, diverse, values, or all to export all three variants in one pass.
- Blend control: continuous or step transitions between samples.
- Automatic organization: moves created and/or used assets into subdirectories to keep things tidy.


## Config

| type           | mandatory | label                     | input type                          | description                                                                                      | if empty          |
|----------------|-----------|---------------------------|-------------------------------------|--------------------------------------------------------------------------------------------------|-------------------|
| GLOBAL         |           |                           |                                     |                                                                                                  |                   |
|                | no        | auto_save                 | true/false                          | auto-saves unsaved assets before processing                                                      | just logs unsaved |
|                | no        | show_details              | true/false                          | shows additional info in logs                                                                    | false             |
|                | no        | debug                     | true/false                          | enables debug mode                                                                               | false             |
| GENERATORS     |           |                           |                                     |                                                                                                  |                   |
|                | no        | unreal_temp_folder        | folder path                         | destination folder for exporting source textures for channel packing                             | /Game/TempFolder  |
|                | no        | backup_folder_name        | folder name                         | moves used files into this subfolder after packing [Content Browser]                             | -                 |
|                | no        | exr_srgb_curve            | true/false                          | applies sRGB gamma curve when converting float texture2D, mimicking Photoshop behaviour          | true              |
|                | no        | delete_used               | true/false                          | deletes used source files after packing                                                          | false             |
| CHANNEL_PACKER |           |                           |                                     |                                                                                                  |                   |
|                | yes       | resize_strategy           | "up"/"down"                         | resolves resolution mismatches within a set, by scaling the textures up or down                  | "down"            |
|                | no        | target_folder_name        | folder name                         | saves generated textures into this subfolder [Content Browser]                                   | -                 |
|                | yes       | mode_name                 | mode id                             | must not be empty to be considered by the function                                               | x                 |
|                | no        | custom_suffix             | suffix name                         | custom suffix for the created textures                                                           | auto              |
|                | no        | texture_compression       | setting name                        | texture compression preset                                                                       | Default           |
|                | no        | sRGB                      | true/false                          | toggles the sRGB flag in the texture settings                                                    | true              |
|                | yes       | channels                  | texture map types                   | textures mapped to each channel of the final generated texture; alpha can be left empty          | x                 |
| CURVE_SAMPLER  |           |                           |                                     |                                                                                                  |                   |
|                | yes       | swatch_count              | >=2 int                             | how many colors to sample from each texture                                                      | 5                 |
|                | yes       | division_method           | "perceptual"/"uniform"              | image's lightness partitioning method                                                            | "perceptual"      |
|                | yes       | export_preset             | "dominant"/"diverse"/"values"/"all" | determines hue sampling priority                                                                 | "values"          |
|                | yes       | light_band_size           | 0-1 float                           | lightness band width for pixel weighting; larger = more color averaging                          | 0.5               |
|                | no        | target_folder             | folder name                         | if set, saves generated curves into this subfolder [Content Browser]                             | -                 |
|                | no        | custom_prefix             | prefix name                         | custom prefix for created Curve assets                                                           | "CC"              |
|                | no        | step_transition           | true/false                          | use step transitions between samples instead of smooth interpolation                             | false             |
|                | no        | use_full_resolution       | true/false                          | if false, downscales the image for speed; set true to samples at full resolution                 | false             |
|                | no        | create_curve_atlas        | true/false                          | if true, creates Curve Atlas for each sampled texture, and assigns all generated curves to each. | false             |
|                | no        | custom_curve_atlas_prefix | prefix name                         | custom prefix for created Curve Atlas                                                            | "CA"              |

---

Channel Packer supported map types:
AO, Roughness, Metalness, Height, Mask, Translucency
Specular, Normal, BentNormal, Bump, Albedo, SSS, Emissive, Glossiness
Config sections: Global, Generators, Channel Packer

Channel Packer Texture compression types: 
Default, Normalmap, Masks, Grayscale, Displacementmap

To add more map types, add their name, suffixes, and default values to TEXTURE_CONFIG in settings.py.

Linear Color Curve Sampler division method:  
- perceptual - partitions lightness using a visually weighted distribution, denser keys where the image perceptual changes more.  
- uniform - partitions lightness evenly across the 0–1 range.

Linear Color Curve Sampler export presets:
- dominant - favors the most prevalent hues, picks the color that dominates each band.
- diverse - maximizes color variety, spreads samples across different hues by repelling previously chosen ones.
- values - prioritizes lightness levels.
- all - exports three curves each with different preset.