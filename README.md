# quillustrate
Odds and ends to interface with Quill, the VR drawing application

## Setup

Requires the following executables available in path:

* blender.exe
* UE4Editor-Cmd.exe
* QuillExporter.exe


## Running

### Converting Quill binary to Quill ascii format

```sh
python3 bin/quill_converter.py --input <QuillProjectDirInput> --output <QuillProjectDirOutput>
```

### Exporting an Alembic File from Quill (Manually)

Export an Alembic (.abc) file, selecting:

* Format: "Alembic"
* Color Space: "Linear"
* "Export Mesh"
* "Export Animation"


![quill_abc_export](docs/images/quill_abc_export.png)

Save where desired.

### Importing Quill Alembic into Blender

```sh
blender.exe --background --python "quillustrate/blender.py" -- --alembic "assets/quill_export_example.abc"
```
