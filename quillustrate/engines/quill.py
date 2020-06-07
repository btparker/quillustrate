import os
import json
import codecs
import struct
from enum import Enum
from quillustrate.engines.engine import Engine

# Thanks to Joan Charmant for the Quill File format info
# http://joancharmant.com/blog/turning-real-scenes-into-vr-paintings/

class BrushType(object):
    MAPPING = {
        0: "LINE",
        1: "RIBBON",
        2: "CYLINDER",
        3: "ELLIPSE",
        4: "CUBE",
    }
    def __init__(self, code):
        self.code = code
        self.name = self.MAPPING[code]

    @classmethod
    def from_name(cls, name):
        code = dict(map(reversed, cls.MAPPING.items()))[name]
        return BrushType(code)

    @classmethod
    def from_code(cls, code):
        return BrushType(code)


class QuillBinaryDecoder(object):
    DECODER_MAPPINGS = {
        "int16": (lambda bin: QuillBinaryDecoder.unpack('h', bin)),
        "int32": (lambda bin: QuillBinaryDecoder.unpack('i', bin)),
        "float": (lambda bin: QuillBinaryDecoder.unpack('f', bin)),
        "bool": (lambda bin: QuillBinaryDecoder.unpack('?', bin)),
    }

    @classmethod
    def unpack(cls, unpack_type, binary_chunk):
        value, = struct.unpack(unpack_type, binary_chunk)
        return value

    @classmethod
    def decode_value_from_binary(cls, value_type, binary_chunk):
        return cls.DECODER_MAPPINGS[value_type](binary_chunk)


class QuillObject(object):
    OFFSETS = {}

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    def to_binary(self):
        # offsets = [item["offset"] for (k, item) in self.OFFSETS.items()]
        binary_data = b'\x00\xFF\x00\xFF'
        base64_data = codecs.encode(binary_data, 'base64')
        return base64_data

    @classmethod
    def get_sorted_offset_items(cls):
        return sorted(cls.OFFSETS.items(), key=lambda x: x[1]["offset"])

    @classmethod
    def generate_offset_datum(cls, binary_data, quill_object_offset, offset_item):
        start = quill_object_offset + offset_item["offset"]
        end = quill_object_offset + offset_item["offset"] + offset_item["size"]
        binary_chunk = binary_data[start:end]
        value = QuillBinaryDecoder.decode_value_from_binary(offset_item["type"], binary_chunk)

        return {
            "offset": offset_item["offset"],
            "global_offset": start,
            "size": offset_item["size"],
            "type": offset_item["type"],
            "value": value,
        }

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        pass


class QuillFileObject(QuillObject):
    OFFSETS = {
        "highest_global_stroke_id": {"offset": 0x00, "size": 4, "type": "int32", "description": "Highest global stroke id"},
        "unknown0x04": {"offset": 0x04, "size": 4, "type": "int32", "description": "Unknown"},
        "drawings": {"offset": 0x08, "size": None, "type": "list[Drawing]", "description": "Start of list of drawings"},
    }

    def __init__(self, highest_global_stroke_id, drawings):
        self.highest_global_stroke_id = highest_global_stroke_id
        self.drawings = drawings

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        json_data = {}
        for offset_item_key, offset_item in cls.get_sorted_offset_items():
            if offset_item_key == "drawings":
                json_data["drawings"] = []
                curr_offset = quill_object_offset + offset_item["offset"]
                while True:
                    drawing = QuillDrawingObject.from_binary(binary_data, curr_offset)
                    json_data["drawings"].append(drawing.to_json())
                    # TODO: more than one
                    break
            else:
                json_data[offset_item_key] = cls.generate_offset_datum(binary_data, quill_object_offset, offset_item)
        return QuillFileObject.from_json(json_data)

    @classmethod
    def from_json(cls, data):
        drawings = list(map(QuillDrawingObject.from_json, data["drawings"]))
        return cls(
            highest_global_stroke_id=data["highest_global_stroke_id"],
            drawings=drawings,
        )

    def to_json(self):
        return {
            "highest_global_stroke_id": self.highest_global_stroke_id,
            "drawings": list(map(QuillDrawingObject.to_json, self.drawings)),
        }

class QuillDrawingObject(QuillObject):
    OFFSETS = {
        "num_strokes": {"offset": 0x00, "size": 4, "type": "int32", "description": "Number of strokes in the drawing"},
        "strokes": {"offset": 0x04, "size": None, "type": "list[Stroke]", "description": "Start of list of strokes"},
    }

    def __init__(self, strokes):
        self.strokes = strokes

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        json_data = {}
        json_data["num_strokes"] = cls.generate_offset_datum(binary_data, quill_object_offset, cls.OFFSETS["num_strokes"])
        json_data["strokes"] = []
        curr_offset = quill_object_offset + cls.OFFSETS["strokes"]["offset"]
        for _ in range(json_data["num_strokes"]["value"]):
            stroke = QuillStrokeObject.from_binary(binary_data, curr_offset)
            json_data["strokes"].append(stroke.to_json())
            # TODO: need to do size offset increment
            break
        return QuillDrawingObject.from_json(json_data)

    @classmethod
    def from_json(cls, data):
        strokes = list(map(QuillStrokeObject.from_json, data["strokes"]))
        return cls(strokes=strokes)

    def to_json(self):
        return {
            "num_strokes":len(self.strokes),
            "strokes": list(map(QuillStrokeObject.to_json, self.strokes)),
        }


class QuillStrokeObject(QuillObject):
    OFFSETS = {
        "global_stroke_id": {"offset": 0x00, "size": 4, "type": "int32", "description": "Global stroke id"},
        "unknown0x04": {"offset": 0x04, "size": 4, "type": "int32", "description": "Unknown"},
        "stroke_bounding_box": {"offset": 0x08, "size": 24, "type": "Bbox", "description": "Bounding box of the stroke"},
        "brush_type": {"offset": 0x20, "size": 2, "type": "int16", "description": "Brush type"},
        "disable_rotational_opacity": {"offset": 0x22, "size": 1, "type": "bool", "description": "Disable rotational opacity"},
        "unknown0x27": {"offset": 0x23, "size": 1, "type": "bool", "description": "Unknown"},
        "num_vertices": {"offset": 0x24, "size": 4, "type": "int32", "description": "Number of vertices in the stroke"},
        "vertices": {"offset": 0x28, "size": None, "type": "list[Vertex]", "description": "Start of list of vertices"},
    }

    def __init__(self, global_stroke_id, stroke_bounding_box, brush_type, disable_rotational_opacity, vertices):
        self.global_stroke_id = global_stroke_id
        self.stroke_bounding_box = stroke_bounding_box
        self.brush_type = brush_type
        self.disable_rotational_opacity = disable_rotational_opacity
        self.vertices = vertices

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        json_data = {}
        for offset_item_key, offset_item in cls.get_sorted_offset_items():
            curr_offset = quill_object_offset + cls.OFFSETS[offset_item_key]["offset"]
            if offset_item_key == "vertices":
                json_data["vertices"] = []
                for _ in range(json_data["num_vertices"]["value"]):
                    vertex = QuillVertexObject.from_binary(binary_data, curr_offset)
                    json_data["vertices"].append(vertex.to_json())
                    curr_offset += QuillVertexObject.get_size()
            elif offset_item_key == "stroke_bounding_box":
                json_data[offset_item_key] = QuillBBoxObject.from_binary(binary_data, curr_offset).to_json()
            else:
                json_data[offset_item_key] = cls.generate_offset_datum(binary_data, quill_object_offset, offset_item)

            if offset_item_key == "brush_type":
                brush_type_code = json_data["brush_type"]["value"]
                json_data[offset_item_key] = BrushType(brush_type_code).name

        return QuillStrokeObject.from_json(json_data)

    @classmethod
    def from_json(cls, data):
        vertices = list(map(QuillVertexObject.from_json, data["vertices"]))
        brush_type = BrushType.from_name(data["brush_type"])
        return cls(
            global_stroke_id=data["global_stroke_id"],
            stroke_bounding_box=data["stroke_bounding_box"],
            brush_type=brush_type,
            disable_rotational_opacity=data["disable_rotational_opacity"],
            vertices=vertices,
        )

    def to_json(self):
        return {
            "global_stroke_id": self.global_stroke_id,
            "stroke_bounding_box": self.stroke_bounding_box,
            "brush_type": self.brush_type.name,
            "disable_rotational_opacity": self.disable_rotational_opacity,
            "num_vertices": len(self.vertices),
            "vertices": list(map(QuillVertexObject.to_json, self.vertices)),
        }


class QuillBBoxObject(QuillObject):
    OFFSETS = {
        "min_x": {"offset": 0x00, "size": 4, "type": "float", "description": "min x"},
        "max_x": {"offset": 0x04, "size": 4, "type": "float", "description": "max x"},
        "min_y": {"offset": 0x08, "size": 4, "type": "float", "description": "min y"},
        "max_y": {"offset": 0x0C, "size": 4, "type": "float", "description": "max y"},
        "min_z": {"offset": 0x10, "size": 4, "type": "float", "description": "min z"},
        "max_z": {"offset": 0x14, "size": 4, "type": "float", "description": "max z"},
    }

    def __init__(self, min_x, max_x, min_y, max_y, min_z, max_z):
        self.min_x = min_x
        self.max_x = max_x
        self.min_y = min_y
        self.max_y = max_y
        self.min_z = min_z
        self.max_z = max_z

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        json_data = {}
        for offset_item_key, offset_item in cls.get_sorted_offset_items():
            json_data[offset_item_key] = cls.generate_offset_datum(binary_data, quill_object_offset, offset_item)
        return QuillBBoxObject.from_json(json_data)

    @classmethod
    def from_json(cls, data):
        return cls(
            min_x=data["min_x"],
            max_x=data["max_x"],
            min_y=data["min_y"],
            max_y=data["max_y"],
            min_z=data["min_z"],
            max_z=data["max_z"],
        )

    def to_json(self):
        return {
            "min_x": self.min_x,
            "max_x": self.max_x,
            "min_y": self.min_y,
            "max_y": self.max_y,
            "min_z": self.min_z,
            "max_z": self.max_z,
        }

class QuillVertexObject(QuillObject):
    OFFSETS = {
        "position": {"offset": 0x00, "size": 12, "type": "vec3", "description": "Position"},
        "normal": {"offset": 0x0C, "size": 12, "type": "vec3", "description": "Normal"},
        "tangent": {"offset": 0x18, "size": 12, "type": "vec3", "description": "Tangent"},
        "color": {"offset": 0x24, "size": 12, "type": "vec3", "description": "Color"},
        "opacity": {"offset": 0x30, "size": 4, "type": "float", "description": "Opacity"},
        "width": {"offset": 0x34, "size": 4, "type": "float", "description": "Width"},
    }
    def __init__(self, position, normal, tangent, color, opacity, width):
        self.position = position
        self.normal = normal
        self.tangent = tangent
        self.color = color
        self.opacity = opacity
        self.width = width

    @classmethod
    def get_size(cls):
        return sum(item['size'] for k, item in cls.OFFSETS.items())

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        json_data = {}
        for offset_item_key, offset_item in cls.get_sorted_offset_items():
            curr_offset = quill_object_offset + cls.OFFSETS[offset_item_key]["offset"]
            if offset_item["type"] == "vec3":
                json_data[offset_item_key] = QuillVec3Object.from_binary(binary_data, curr_offset).to_json()
            else:
                json_data[offset_item_key] = cls.generate_offset_datum(binary_data, quill_object_offset, offset_item)
        return QuillVertexObject.from_json(json_data)

    @classmethod
    def from_json(cls, data):
        return cls(
            position=data["position"],
            normal=data["normal"],
            tangent=data["tangent"],
            color=data["color"],
            opacity=data["opacity"],
            width=data["width"],
        )

    def to_json(self):
        return {
            "position": self.position,
            "normal": self.normal,
            "tangent": self.tangent,
            "color": self.color,
            "opacity": self.opacity,
            "width": self.width,
        }

class QuillVec3Object(QuillObject):
    OFFSETS = {
        "x": {"offset": 0x00, "size": 4, "type": "float", "description": "X"},
        "y": {"offset": 0x04, "size": 4, "type": "float", "description": "Y"},
        "z": {"offset": 0x08, "size": 4, "type": "float", "description": "Z"},
    }
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    @classmethod
    def from_binary(cls, binary_data, quill_object_offset=0):
        json_data = {}
        for offset_item_key, offset_item in cls.get_sorted_offset_items():
            json_data[offset_item_key] = cls.generate_offset_datum(binary_data, quill_object_offset, offset_item)
        return QuillVec3Object.from_json(json_data)

    @classmethod
    def from_json(cls, data):
        return cls(
            x=data["x"],
            y=data["y"],
            z=data["z"],
        )

    def to_json(self):
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }


class QuillSceneData(object):
    def __init__(self, proj_dir):
        input_quill_json_path = os.path.join(proj_dir, 'Quill.json')
        with open(input_quill_json_path, 'r') as json_file:
            self.data = json.load(json_file)

    def write(self, output_dir):
        quill_json_path = os.path.join(output_dir, 'Quill.json')
        with open(quill_json_path, 'w') as outfile:
            json.dump(self.data, outfile, indent=1)


class QuillStateData(object):
    def __init__(self, proj_dir):
        input_state_json_path = os.path.join(proj_dir, 'State.json')
        with open(input_state_json_path, 'r') as json_file:
            self.data = json.load(json_file)

    def write(self, output_dir):
        state_json_path = os.path.join(output_dir, 'State.json')
        with open(state_json_path, 'w') as outfile:
            json.dump(self.data, outfile, indent=1)


class QuillFileData(object):
    def __init__(self, proj_dir):
        input_quill_qbin_path = os.path.join(proj_dir, 'Quill.qbin')
        with open(input_quill_qbin_path, 'rb') as binary_file:
            self.raw_data = binary_file.read()

        self.file_object = QuillFileObject.from_binary(self.raw_data)

    def write(self, output_dir):
        # Write both
        self.write_binary(output_dir)
        self.write_ascii(output_dir)

    def to_json(self):
        return self.file_object.to_json()

    def write_binary(self, output_dir):
        quill_qbin_path = os.path.join(output_dir, 'Quill.qbin')
        with open(quill_qbin_path, 'wb') as binary_file:
            binary_file.write(self.file_object.to_binary())

    def write_ascii(self, output_dir):
        quill_qa_path = os.path.join(output_dir, 'Quill.qa')
        with open(quill_qa_path, 'w') as outfile:
            json.dump(self.file_object.to_json(), outfile, indent=1)


class QuillProject(object):
    def __init__(self, proj_dir):
        self.scene_data = QuillSceneData(proj_dir)
        self.state_data = QuillStateData(proj_dir)
        self.file_data = QuillFileData(proj_dir)

    def write(self, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        self.scene_data.write(output_dir)
        self.state_data.write(output_dir)
        self.file_data.write(output_dir)


class QuillConverterEngine(object):
    @classmethod
    def bin_to_ascii(cls, input_proj_dir, output_proj_dir):
        QuillProject(proj_dir=input_proj_dir).write(output_proj_dir)


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
