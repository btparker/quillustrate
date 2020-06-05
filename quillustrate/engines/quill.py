import os
import json
import codecs
from enum import Enum
from quillustrate.engines.engine import Engine


class BrushTypes(Enum):
    LINE = 0
    RIBBON = 1
    CYLINDER = 2
    ELLIPSE = 3
    CUBE = 4


class QuillObject(object):
    OFFSETS = {}

    def __init__(self, **args):
        # Don't love this, but helps with a 'to_qa' procedural export
        self.data = {}
        for (k,v) in args.items():
            self.data[k] = v

    def to_qa(self):
        return self.data

    def to_qbin(self):
        # TODO: Not a dummy method
        offsets = [item["offset"] for (k, item) in self.OFFSETS.items()]
        binary_data = b'\x00\xFF\x00\xFF'
        base64_data = codecs.encode(binary_data, 'base64')
        return base64_data


class QuillFile(QuillObject):
    OFFSETS = {
        "highest_global_stroke_id": {"offset": 0x00, "size": 4, "type": "int32", "description": "Highest global stroke id"},
        # UNKNOWN: {"offset": 0x04, "size": 4, "type": "?", "description": "Unknown"},
        "drawings": {"offset": 0x08, "size": '?', "type": "Array<Drawing>", "description": "Start of array of drawings"},
    }

    def __init__(self, drawings=[], highest_global_stroke_id=None):
        super(QuillFile, self).__init__(
            highest_global_stroke_id=highest_global_stroke_id,
            drawings=drawings,
        )

    @classmethod
    def from_qbin(self, qbin):
        return QuillFile()

    @classmethod
    def from_qa(self, qa):
        return QuillFile()


class QuillDrawing(QuillObject):
    OFFSETS = {
        "num_strokes": {"offset": 0x00, "size": 4, "type": "int32", "description": "Number of strokes in the drawing"},
        "strokes": {"offset": 0x00, "size": '?', "type": "Array<Stroke>", "description": "Start of array of strokes"},
    }

    def __init__(self, strokes=[]):
        super(QuillFile, self).__init__(
            strokes=strokes,
        )


class QuillStroke(QuillObject):
    OFFSETS = {
        "global_stroke_id": {"offset": 0x00, "size": 4, "type": "int32", "description": "Global stroke id"},
        # UNKNOWN: {"offset": 0x04, "size": 4, "type": "?", "description": "Unknown"},
        "stroke_bounding_box": {"offset": 0x08, "size": 24, "type": "Bbox", "description": "Bounding box of the stroke"},
        # Brush type enumeration: 0: Line, 1: Ribbon, 2: Cylinder, 3: Ellipse, 4: Cube.
        "brush_type": {"offset": 0x24, "size": 2, "type": "int16", "description": "Brush type"},
        "disable_rotational_opacity": {"offset": 0x26, "size": 1, "type": "bool", "description": "Disable rotational opacity"},
        # UNKNOWN: {"offset": 0x27, "size": 1, "type": "?", "description": "Unknown"},
        "num_vertices": {"offset": 0x28, "size": 4, "type": "int32", "description": "Number of vertices in the stroke"},
        "vertices": {"offset": 0x2C, "size": '?', "type": "Array<Vertex>", "description": "Start of array of vertices"},
    }

    def __init__(self, brush_type=BrushTypes.LINE, vertices=[], disable_rotational_opacity=True, global_stroke_id=None, stroke_bounding_box=None):
        super(QuillStroke, self).__init__(
            brush_type=brush_type,
            vertices=vertices,
            disable_rotational_opacity=disable_rotational_opacity,
            global_stroke_id=global_stroke_id,
            stroke_bounding_box=stroke_bounding_box,
        )


class QuillBBox(QuillObject):
    OFFSETS = {
        "min_x": {"offset": 0x00, "size": 4, "type": "float", "description": "min x"},
        "max_x": {"offset": 0x04, "size": 4, "type": "float", "description": "max x"},
        "min_y": {"offset": 0x08, "size": 4, "type": "float", "description": "min y"},
        "max_y": {"offset": 0x0C, "size": 4, "type": "float", "description": "max y"},
        "min_z": {"offset": 0x10, "size": 4, "type": "float", "description": "min z"},
        "max_z": {"offset": 0x14, "size": 4, "type": "float", "description": "max z"},
    }

    def __init__(self, min_x=0.0, max_x=0.0, min_y=0.0, max_y=0.0, min_z=0.0, max_z=0.0):
        super(QuillBBox, self).__init__(
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            min_z=min_z,
            max_z=max_z,
        )


class QuillVertex(QuillObject):
    OFFSETS = {
        "position": {"offset": 0x00, "size": 12, "type": "vec3", "description": "Position"},
        "normal": {"offset": 0x0C, "size": 12, "type": "vec3", "description": "Normal"},
        "tangent": {"offset": 0x18, "size": 12, "type": "vec3", "description": "Tangent"},
        "color": {"offset": 0x24, "size": 12, "type": "vec3", "description": "Color"},
        "opacity": {"offset": 0x30, "size": 4, "type": "float", "description": "Opacity"},
        "width": {"offset": 0x34, "size": 4, "type": "float", "description": "Width"},
    }

    def __init__(self,
        position=None,
        normal=None,
        tangent=None,
        color=None,
        opacity=None,
        width=None,
    ):
        super(QuillBBox, self).__init__(
            position=position,
            normal=normal,
            tangent=tangent,
            color=color,
            opacity=opacity,
            width=width,
        )


class QuillProject(object):
    def __init__(self, state_data, scene_data, quill_file):
        self.state_data = state_data
        self.scene_data = scene_data
        self.quill_file = quill_file

    def write(self, output):
        if not os.path.exists(output):
            os.makedirs(output)

        quill_json_path = os.path.join(output, 'Quill.json')
        with open(quill_json_path, 'w') as outfile:
            json.dump(self.scene_data, outfile, indent=1)

        state_json_path = os.path.join(output, 'State.json')
        with open(state_json_path, 'w') as outfile:
            json.dump(self.state_data, outfile, indent=1)

        quill_qbin_path = os.path.join(output, 'Quill.qbin')
        with open(quill_qbin_path, 'wb') as binary_file:
            binary_file.write(self.quill_file.to_qbin())

        quill_qa_path = os.path.join(output, 'Quill.qa')
        with open(quill_qa_path, 'w') as outfile:
            json.dump(self.quill_file.to_qa(), outfile, indent=1)


class QuillConverterEngine(object):
    @classmethod
    def bin_to_ascii(cls, input_proj_dir, output_proj_dir):
        input_state_json_path = os.path.join(input_proj_dir, 'State.json')
        with open(input_state_json_path) as json_file:
            quill_state_data = json.load(json_file)

        input_quill_json_path = os.path.join(input_proj_dir, 'Quill.json')
        with open(input_quill_json_path) as json_file:
            quill_scene_data = json.load(json_file)

        input_quill_qbin_path = os.path.join(input_proj_dir, 'Quill.qbin')
        with open(input_quill_qbin_path) as binary_file:
            quill_scene_bin = binary_file.read()

        quill_project = QuillProject(
            state_data=quill_state_data,
            scene_data=quill_scene_data,
            quill_file=QuillFile.from_qbin(quill_scene_bin),
        )

        quill_project.write(output_proj_dir)


class QuillExporterEngine(Engine):
    command_string = "QuillExporter.exe"

    def load_template(self):
        import json

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'assets',
            'quill-export-template.json',
        )

        return json.load(open(template_path))

    def save_settings(settings, output_path):
        with open(output_path, "w") as settings_file:
            json.dump(
                settings,
                settings_file,
                indent=4,
                sort_keys=True,
            )

    def run(self, settings_path):
        self.run_cmd([settings_path])
