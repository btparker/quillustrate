import os
import json
import codecs
import struct
from enum import Enum
import ctypes
from typing import List
from functools import reduce
from quillustrate.engines.engine import Engine

# Thanks to Joan Charmant for the Quill File format info
# http://joancharmant.com/blog/turning-real-scenes-into-vr-paintings/

class QuillType(Enum):
    INT16 = ("int16", 2)
    INT32 = ("int32", 4)
    FLOAT = ("float", 4)
    BOOL = ("bool", 1)
    BRUSH_TYPE = ("brush_type", 2)
    BBOX = ("bbox", 24)
    VERTEX = ("vertex", 56)
    VEC3 = ("vec3", 12)
    DRAWING = ("drawing", None)
    STROKE = ("stroke", None)

    def __init__(self, key, size):
        self.key = key
        self.size = size


class QuillBrushType(object):
    MAPPING = {
        0: "LINE",
        1: "RIBBON", # ROUNDED_RIBBON
        2: "CYLINDER", # CAPPED_CYLINDER
        3: "ELLIPSE", # CAPPED_ELLIPSE
        4: "CUBE",
    }
    def __init__(self, code):
        self.code = code
        self.name = self.MAPPING[code]

    @classmethod
    def from_name(cls, name) -> object:
        code = dict(map(reversed, cls.MAPPING.items()))[name]
        return cls(code)

    @classmethod
    def from_code(cls, code) -> object:
        return cls(code)

    @classmethod
    def decode(cls, binary_chunk) -> object:
        code = QuillBinaryDecoder.decode_value(QuillType.INT16, binary_chunk)
        return cls(code)

    def json_encode(self):
        return self.name

    def encode(self):
        return QuillBinaryEncoder.encode_value(QuillType.INT16, self.code)


class QuillJsonEncoder(object):
    def run(self, quill_object):
        return self.encode(quill_object)

    def encode(self, quill_object):
        data = {}
        for k, item in quill_object.OFFSETS.items():
            if not hasattr(quill_object, k):
                continue

            quill_object_attr = getattr(quill_object, k)

            if isinstance(quill_object_attr, list):
                child_items = quill_object_attr
                value = []
                for child_item in child_items:
                    value.append(self.encode(child_item))
            elif isinstance(quill_object_attr, QuillObject):
                value = self.encode(quill_object_attr)
            elif hasattr(quill_object_attr, "json_encode"):
                value = quill_object_attr.json_encode()
            else:
                value = quill_object_attr

            data[k] = value

        return data

class QuillBinaryEncoder(object):
    ENCODER_VALUE_MAPPINGS = {
        QuillType.INT16: (lambda value: QuillBinaryEncoder.pack('h', value)),
        QuillType.INT32: (lambda value: QuillBinaryEncoder.pack('i', value)),
        QuillType.FLOAT: (lambda value: QuillBinaryEncoder.pack('f', value)),
        QuillType.BOOL: (lambda value: QuillBinaryEncoder.pack('?', value)),
        QuillType.BRUSH_TYPE: (lambda brush_type: brush_type.encode()),
    }

    def run(self, quill_object):
        size = quill_object.get_binary_size()
        print("Estimated Quill object size: {} bytes of data".format(size))
        binary_data = self.encode(quill_object)
        print("Encoded: {} bytes".format(len(binary_data)))
        return binary_data

    def encode(self, quill_object):
        binary = b''
        for k, item in quill_object.OFFSETS.items():
            if not hasattr(quill_object, k):
                continue

            quill_object_attr = getattr(quill_object, k)

            if isinstance(quill_object_attr, list):
                child_items = quill_object_attr
                for child_item in child_items:
                    binary += self.encode(child_item)
            elif isinstance(quill_object_attr, QuillObject):
                binary += self.encode(quill_object_attr)
            elif hasattr(quill_object_attr, "encode"):
                binary += quill_object_attr.encode()
            else:
                binary += self.encode_value(item["type"], quill_object_attr)

        return binary

    @classmethod
    def encode_value(cls, value_type, value):
        return cls.ENCODER_VALUE_MAPPINGS[value_type](value)

    @classmethod
    def pack(cls, unpack_type, value):
        return struct.pack(unpack_type, value)

class QuillBinaryDecoder(object):
    DECODER_VALUE_MAPPINGS = {
        QuillType.INT16: (lambda bin: QuillBinaryDecoder.unpack('h', bin)),
        QuillType.INT32: (lambda bin: QuillBinaryDecoder.unpack('i', bin)),
        QuillType.FLOAT: (lambda bin: QuillBinaryDecoder.unpack('f', bin)),
        QuillType.BOOL: (lambda bin: QuillBinaryDecoder.unpack('?', bin)),
        QuillType.BRUSH_TYPE: (lambda bin: QuillBrushType.decode(bin)),
    }

    def __init__(self, binary_data):
        self.binary_data = binary_data

    def run(self):
        return self.decode(QuillFileObject, self.binary_data)

    @classmethod
    def decode(cls, quill_object_cls, binary_data, quill_object_offset=0):

        # Edge case where the base file is an empty binary
        if len(binary_data) == 0:
            return None

        # Scaffolding data from offset descriptors
        data = dict(quill_object_cls.OFFSETS)

        # Gathering all QuillObject subclasses in order to construct from type
        QO_SUBCLASSES = QuillObject.__subclasses__()

        # Calculating 'global_offset' per item
        update_global_offset = lambda v: dict(
            v,
            **{'global_offset': v["offset"] + quill_object_offset},
        )
        data = dict([(k,update_global_offset(v)) for k,v in data.items()])

        is_quill_object_type = lambda v: v["type"] in [qo.TYPE for qo in QO_SUBCLASSES]

        # Calculating 'primitive' values
        is_primitive = lambda v: not is_quill_object_type(v)

        def update_primitive_value(offset_item):
            start = offset_item["global_offset"]
            value = cls.decode_value(offset_item["type"], binary_data[start:])
            return dict(offset_item, **{'value': value})

        data = dict([(k,update_primitive_value(v) if is_primitive(v) else v) for k,v in data.items()])

        # Calculating QuillObject values
        is_sequence = lambda v: "sequence" in v and v["sequence"]
        is_sequence_length = lambda v: "sequence_length" in v and v["sequence_length"]
        def update_quill_object_value(offset_item):
            child_quill_object_cls = next((c for c in QO_SUBCLASSES if c.TYPE == offset_item["type"]))
            start = offset_item["global_offset"]
            if is_sequence(offset_item):
                # If sequence length is defined, use it. If not, will go to end of binary data
                quill_objects_remaining = next((v["value"] for k,v in data.items() if is_sequence_length(v)), None)
                child_quill_objects = []
                while True:
                    child_quill_object = cls.decode(child_quill_object_cls, binary_data[start:])
                    if child_quill_object is None:
                        break
                    child_quill_objects.append(child_quill_object)
                    start += child_quill_object.get_binary_size()
                    # Decrement quill objects remaining, break when zero
                    if quill_objects_remaining is not None:
                        quill_objects_remaining -= 1
                        if quill_objects_remaining <= 0:
                            break
                    if start >= len(binary_data):
                        break
                value = child_quill_objects
            else:
                value = cls.decode(child_quill_object_cls, binary_data[start:])

            return dict(offset_item, **{'value': value})
        data = dict([(k,update_quill_object_value(v) if is_quill_object_type(v) else v) for k,v in data.items()])

        # Generating the key:value argumenmts from the decoded data
        args = dict([(k,v["value"]) for k,v in data.items()])
        return quill_object_cls(**args)

    @classmethod
    def unpack(cls, unpack_type, binary_chunk):
        value, = struct.unpack(unpack_type, binary_chunk)
        return value

    @classmethod
    def decode_value(cls, value_type, binary_data):
        binary_chunk = binary_data[:value_type.size]
        return cls.DECODER_VALUE_MAPPINGS[value_type](binary_chunk)


class QuillObject(object):
    OFFSETS = {}
    TYPE = None
    def __init__(self, **args):
        for (field, value) in args.items():
            setattr(self, field, value)

    def get_binary_size(self):
        binary_size = 0
        for k, item in self.OFFSETS.items():
            is_list = isinstance(getattr(self, k), list)
            if item["type"].size is not None and not is_list:
                binary_size += item["type"].size
            elif is_list:
                for child_item in getattr(self, k):
                    binary_size += child_item.get_binary_size()
        return binary_size

class QuillFileObject(QuillObject):
    OFFSETS = {
        "highest_global_stroke_id": {"offset": 0x00, "type": QuillType.INT32, "description": "Highest global stroke id"},
        "unknown0x04": {"offset": 0x04, "type": QuillType.INT32, "description": "Unknown"},
        "drawings": {"offset": 0x08, "type": QuillType.DRAWING, "sequence": True, "description": "Start of list of drawings"},
    }

class QuillDrawingObject(QuillObject):
    TYPE = QuillType.DRAWING
    OFFSETS = {
        "num_strokes": {"offset": 0x00, "type": QuillType.INT32, "sequence_length": True, "description": "Number of strokes in the drawing"},
        "strokes": {"offset": 0x04, "type": QuillType.STROKE, "sequence": True, "description": "Start of list of strokes"},
    }


class QuillStrokeObject(QuillObject):
    TYPE = QuillType.STROKE
    OFFSETS = {
        "global_stroke_id": {"offset": 0x00, "type": QuillType.INT32, "description": "Global stroke id"},
        "unknown0x04": {"offset": 0x04, "type": QuillType.INT32, "description": "Unknown"},
        "stroke_bounding_box": {"offset": 0x08, "size": 24, "type": QuillType.BBOX, "description": "Bounding box of the stroke"},
        "brush_type": {"offset": 0x20, "size": 2, "type": QuillType.BRUSH_TYPE, "description": "Brush type"},
        "disable_rotational_opacity": {"offset": 0x22, "type": QuillType.BOOL, "description": "Disable rotational opacity"},
        "unknown0x27": {"offset": 0x23, "type": QuillType.BOOL, "description": "Unknown"},
        "num_vertices": {"offset": 0x24, "type": QuillType.INT32, "sequence_length": True, "description": "Number of vertices in the stroke"},
        "vertices": {"offset": 0x28, "type": QuillType.VERTEX, "sequence": True, "description": "Start of list of vertices"},
    }


class QuillBBoxObject(QuillObject):
    TYPE = QuillType.BBOX
    OFFSETS = {
        "min_x": {"offset": 0x00, "type": QuillType.FLOAT, "description": "min x"},
        "max_x": {"offset": 0x04, "type": QuillType.FLOAT, "description": "max x"},
        "min_y": {"offset": 0x08, "type": QuillType.FLOAT, "description": "min y"},
        "max_y": {"offset": 0x0C, "type": QuillType.FLOAT, "description": "max y"},
        "min_z": {"offset": 0x10, "type": QuillType.FLOAT, "description": "min z"},
        "max_z": {"offset": 0x14, "type": QuillType.FLOAT, "description": "max z"},
    }

class QuillVertexObject(QuillObject):
    TYPE = QuillType.VERTEX
    OFFSETS = {
        "position": {"offset": 0x00, "type": QuillType.VEC3, "description": "Position"},
        "normal": {"offset": 0x0C, "type": QuillType.VEC3, "description": "Normal"},
        "tangent": {"offset": 0x18, "type": QuillType.VEC3, "description": "Tangent"},
        "color": {"offset": 0x24, "type": QuillType.VEC3, "description": "Color"},
        "opacity": {"offset": 0x30, "type": QuillType.FLOAT, "description": "Opacity"},
        "width": {"offset": 0x34, "type": QuillType.FLOAT, "description": "Width"},
    }

class QuillVec3Object(QuillObject):
    TYPE = QuillType.VEC3
    OFFSETS = {
        "x": {"offset": 0x00, "type": QuillType.FLOAT, "description": "X"},
        "y": {"offset": 0x04, "type": QuillType.FLOAT, "description": "Y"},
        "z": {"offset": 0x08, "type": QuillType.FLOAT, "description": "Z"},
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
        if not os.path.exists(input_state_json_path):
            input_state_json_path = os.path.join(proj_dir, '~State.json')
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
            binary_data = binary_file.read()
        self.file_object = QuillBinaryDecoder(binary_data).run()

    def write(self, output_dir):
        # Write both
        self.write_binary(output_dir)
        self.write_ascii(output_dir)

    def to_json(self) -> dict:
        return QuillJsonEncoder().run(self.file_object)

    def to_binary(self):
        return QuillBinaryEncoder().run(self.file_object)

    def write_binary(self, output_dir):
        quill_qbin_path = os.path.join(output_dir, 'Quill.qbin')
        with open(quill_qbin_path, 'wb') as binary_file:
            binary_file.write(self.to_binary())

    def write_ascii(self, output_dir):
        quill_qa_path = os.path.join(output_dir, 'Quill.qa')
        with open(quill_qa_path, 'w') as outfile:
            json.dump(self.to_json(), outfile, indent=1)


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
