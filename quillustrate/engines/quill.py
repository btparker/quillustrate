import os
import json
import codecs
import struct
from enum import Enum
import ctypes
from typing import List
from functools import reduce
from quillustrate.engines.engine import Engine
from collections import OrderedDict
from PIL import Image
import numpy as np

# Thanks to Joan Charmant for the initial Quill File format info
# http://joancharmant.com/blog/turning-real-scenes-into-vr-paintings/

class QuillType(Enum):
    CHAR = ("char", 1)
    INT16 = ("int16", 2)
    INT32 = ("int32", 4)
    FLOAT = ("float", 4)
    BOOL = ("bool", 1)
    BRUSH_TYPE = ("brush_type", 2)
    BBOX = ("bbox", 24)
    VERTEX = ("vertex", 56)
    VEC3 = ("vec3", 12)
    RGBA = ("rgba", 4)
    RGB = ("rgb", 3)
    DRAWING = ("drawing", None)
    PICTURE = ("picture", None)
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
        code = QuillBinaryDecoder.unpack('h', binary_chunk)
        return cls(code)

    def json_encode(self):
        return self.name

    def encode(self):
        return QuillBinaryEncoder.encode_value(QuillType.INT16, self.code)

class QuillJsonEncoder(object):
    def __init__(self, quill_scene):
        self.quill_scene = quill_scene

    def run(self):
        file_json = json.loads(json.dumps(self.quill_scene.quill_scene_obj, cls=QuillObjectJsonEncoder))
        scene_data = self.quill_scene.scene_data_obj.get_data()
        return {
            **scene_data,
        }

class QuillObjectJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, QuillObject):
            quill_object = obj
            data = {}
            for item in quill_object.get_offset_items():
                k = item["field"]
                if not hasattr(quill_object, k):
                    continue
                quill_object_attr = getattr(quill_object, k)
                if isinstance(quill_object_attr, list):
                    data[k] = [self.default(o) for o in quill_object_attr]
                else:
                    data[k] =  quill_object_attr
            return data
        elif isinstance(obj, QuillBrushType):
            return obj.name
        else:
            return json.JSONEncoder.default(self, obj)

class QuillBinaryEncoder(object):
    ENCODER_PRIMITIVE_MAPPINGS = {
        QuillType.CHAR: (lambda value: QuillBinaryEncoder.pack('B', value)),
        QuillType.INT16: (lambda value: QuillBinaryEncoder.pack('h', value)),
        QuillType.INT32: (lambda value: QuillBinaryEncoder.pack('i', value)),
        QuillType.FLOAT: (lambda value: QuillBinaryEncoder.pack('f', value)),
        QuillType.BOOL: (lambda value: QuillBinaryEncoder.pack('?', value)),
        QuillType.BRUSH_TYPE: (lambda brush_type: brush_type.encode()),
    }

    def __init__(self, quill_scene):
        self.quill_scene = quill_scene

    def run(self):
        size = self.quill_scene.quill_file_obj.get_binary_size()
        print("Estimated Quill object size: {} bytes of data".format(size))
        binary_data = self.encode(self.quill_scene.quill_file_obj)
        binary_data_obj = QuillBinaryData(binary_data)
        print("Encoded: {} bytes".format(len(binary_data)))
        return binary_data_obj, self.quill_scene.scene_data_obj

    def encode(self, quill_object):
        binary = b''
        for item in quill_object.get_offset_items():
            k = item["field"]
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
        return cls.ENCODER_PRIMITIVE_MAPPINGS[value_type](value)

    @classmethod
    def pack(cls, unpack_type, value):
        return struct.pack(unpack_type, value)

class QuillBinaryDecoder(object):
    DECODER_PRIMITIVE_MAPPINGS = {
        QuillType.CHAR: (lambda bin_obj: QuillBinaryDecoder.unpack('B', bin_obj.get_data())),
        QuillType.INT16: (lambda bin_obj: QuillBinaryDecoder.unpack('h', bin_obj.get_data())),
        QuillType.INT32: (lambda bin_obj: QuillBinaryDecoder.unpack('i', bin_obj.get_data())),
        QuillType.FLOAT: (lambda bin_obj: QuillBinaryDecoder.unpack('f', bin_obj.get_data())),
        QuillType.BOOL: (lambda bin_obj: QuillBinaryDecoder.unpack('?', bin_obj.get_data())),
        QuillType.BRUSH_TYPE: (lambda bin_obj: QuillBrushType.decode(bin_obj.get_data())),
    }

    def __init__(self, binary_data_obj, scene_data_obj):
        self.binary_data_obj = binary_data_obj
        self.scene_data_obj = scene_data_obj

    def run(self):
        offset = 0
        # Instantiate QuillSceneObject, a special case as the root object
        quill_scene_headers_size = QuillSceneObject.compute_header_binary_size()
        binary_chunk_obj, offset = self.binary_data_obj.chunk(offset, quill_scene_headers_size)
        quill_scene_headers = QuillSceneObject.decode_headers(binary_chunk_obj)
        quill_scene_obj = QuillSceneObject(**quill_scene_headers)
        quill_file_value_offsets = self.scene_data_obj.get_quill_file_value_offsets()

        # Here we add value offsets, as these are determined by the scene_data,
        # unlike other QuillObjects, which are determined by populated headers
        indices = [offset_item["offset"] for offset_item in quill_file_value_offsets]
        indices += [self.binary_data_obj.get_size()]
        sizes = [j-i for i, j in zip(indices[:-1], indices[1:])]
        for file_offset, file_size, file_offset_item in zip(indices, sizes, quill_file_value_offsets):
            binary_chunk_obj, _ = self.binary_data_obj.chunk(file_offset, file_size)
            quill_object_cls = QuillObject.get_class_by_type(file_offset_item["type"])
            quill_object = quill_object_cls.decode(binary_chunk_obj)
            quill_scene_obj.add_value(quill_object)

        print(quill_scene_obj.get_values()[0].get_values()[1].get_values())

        return QuillScene(scene_data_obj=self.scene_data_obj, quill_scene_obj=quill_scene_obj)

    @classmethod
    def unpack(cls, unpack_type, binary_chunk):
        value, = struct.unpack(unpack_type, binary_chunk)
        return value

    @classmethod
    def is_primitive_type(cls, value_type):
        return value_type in cls.DECODER_PRIMITIVE_MAPPINGS

    @classmethod
    def get_sequence_length(cls, data):
        return None

    @classmethod
    def decode_primitive(cls, value_type, binary_chunk_obj):
        if not cls.is_primitive_type(value_type):
            raise Error("''{}'' is not a primitive type".format(value_type))
        if binary_chunk_obj.get_size() != value_type.size:
            raise Error("binary_chunk_obj not equal to type size ({} != {})".format(
                len(binary_chunk_obj),
                value_type.size,
            ))
        return cls.DECODER_PRIMITIVE_MAPPINGS[value_type](binary_chunk_obj)


class QuillObject(object):
    # Header offsets should be immutable
    HEADER_OFFSETS = []
    # Value offsets can change
    VALUE_OFFSETS = []
    TYPE = None

    def __init__(self, **args):
        header_fields = self.get_header_fields()
        # Setting headers (which are required to instantiate)
        for (field, value) in args.items():
            if field in header_fields:
                setattr(self, field, value)
        self.values = []

    def get_binary_size(self):
        binary_size = 0
        binary_size += self.compute_header_binary_size()
        binary_size += self.get_values_binary_size()
        return binary_size

    def get_values_binary_size():
        binary_size = 0
        for value in values:
            value_type = value.get_type()
            if QuillBinaryDecoder.is_primitive_type(value_type):
                binary_size += value.size
            else:
                binary_size += value.get_binary_size()
        return binary_size

    def get_type(self):
        return TYPE

    @classmethod
    def compute_header_binary_size(cls):
        """Because headers are deterministic, this can be a class method"""
        binary_size = 0
        for item in cls.get_header_offset_items():
            k = item["field"]
            binary_size += item["type"].size
        return binary_size

    @classmethod
    def decode_headers(cls, binary_data_obj):
        """Because headers are deterministic, this can be a class method"""
        offset = 0
        headers = {}
        for header_offset_item in cls.get_header_offset_items():
            field = header_offset_item["field"]
            print(field)
            object_cls = QuillObject.get_class_by_type(header_offset_item["type"])
            binary_chunk_obj, offset = binary_data_obj.chunk(offset, header_offset_item["type"].size)
            headers[field] = QuillBinaryDecoder.decode(binary_chunk_obj)
        return headers

    @classmethod
    def decode(cls, binary_data_obj):
        headers_size = cls.compute_header_binary_size()
        headers_binary_chunk_obj, offset = binary_data_obj.chunk(0, headers_size)
        headers = cls.decode_headers(headers_binary_chunk_obj)
        print(headers)
        quill_object = cls(**headers)
        values_binary_chunk_obj, offset = binary_data_obj.chunk(offset, None)
        quill_object.decode_values(values_binary_chunk_obj)
        return quill_object

    def decode_values(self, binary_data_obj):
        offset = 0
        for value_offset_item in self.get_value_offset_items():
            print(value_offset_item)
            if QuillBinaryDecoder.is_primitive_type(value_offset_item["type"]):
                binary_chunk_obj, offset = binary_data_obj.chunk(offset, value_offset_item["type"].size)
                self.values.append(QuillBinaryDecoder.decode_primitive(value_offset_item["type"], binary_chunk_obj))
            else:
                quill_object_cls = QuillObject.get_class_by_type(value_offset_item["type"])
                quill_object = quill_object_cls.decode(binary_data_obj)
                self.values.append(quill_object)

    @classmethod
    def get_class_by_type(cls, type):
        # Gathering all QuillObject subclasses in order to construct from type
        qo_subclasses = QuillObject.__subclasses__()

        # Get the sequence_quill_object_cls by type (if exists)
        return next((qo_cls for qo_cls in qo_subclasses if qo_cls.TYPE == type), None)

    def get_offset_items(self):
        return self.get_header_offset_items() + self.get_value_offset_items()

    @classmethod
    def get_header_offset_items(cls):
        return cls.HEADER_OFFSETS

    @classmethod
    def get_header_fields(cls):
        return [header_offset["field"] for header_offset in cls.get_header_offset_items()]

    def get_value_offset_items(self):
        return self.VALUE_OFFSETS

    def add_value(self, value):
        self.values.append(value)

    def get_values(self):
        return self.values

    def get_sequence_length(self):
        """Default to 1, others override"""
        return 1



class QuillSceneObject(QuillObject):
        HEADER_OFFSETS = [
            {"field": "highest_global_stroke_id", "type": QuillType.INT32, "description": "Highest global stroke id"},
            {"field": "unknown0", "type": QuillType.INT32, "description": "Unknown"},
        ]

class QuillDrawingObject(QuillObject):
    TYPE = QuillType.DRAWING
    HEADER_OFFSETS = [
        {"field": "num_strokes", "type": QuillType.INT32, "description": "Number of strokes in the drawing"},
    ]
    VALUE_OFFSETS = [
        {"field": "strokes", "type": QuillType.STROKE, "description": "A stroke item"},
    ]

    def decode_values(self, binary_data_obj):
        offset = 0
        print(self.num_strokes)
        self.VALUE_OFFSETS = self.VALUE_OFFSETS * self.num_strokes
        print(self.VALUE_OFFSETS)
        super().decode_values(binary_data_obj)


class QuillStrokeObject(QuillObject):
    TYPE = QuillType.STROKE
    HEADER_OFFSETS = [
        {"field": "global_stroke_id", "type": QuillType.INT32, "description": "Global stroke id"},
        {"field": "unknown0", "type": QuillType.INT32, "description": "Unknown"},
        {"field": "stroke_bounding_box", "type": QuillType.BBOX, "description": "Bounding box of the stroke"},
        {"field": "brush_type","type": QuillType.BRUSH_TYPE, "description": "Brush type"},
        {"field": "disable_rotational_opacity", "type": QuillType.BOOL, "description": "Disable rotational opacity"},
        {"field": "unknown1", "type": QuillType.BOOL, "description": "Unknown"},
        {"field": "num_vertices", "type": QuillType.INT32, "description": "Number of vertices in the stroke"},
    ]
    VALUE_OFFSETS =[
        {"field": "vertices", "type": QuillType.VERTEX, "description": "A vertex item"},
    ]

    def decode_values(self, binary_data_obj):
        offset = 0
        print(self.num_vertices)
        self.VALUE_OFFSETS = self.VALUE_OFFSETS * self.num_vertices
        print(self.VALUE_OFFSETS)
        super().decode_values(binary_data_obj)



class QuillBBoxObject(QuillObject):
    TYPE = QuillType.BBOX
    VALUE_OFFSETS = [
        {"field": "min_x", "type": QuillType.FLOAT, "description": "min x"},
        {"field": "max_x", "type": QuillType.FLOAT, "description": "max x"},
        {"field": "min_y", "type": QuillType.FLOAT, "description": "min y"},
        {"field": "max_y", "type": QuillType.FLOAT, "description": "max y"},
        {"field": "min_z", "type": QuillType.FLOAT, "description": "min z"},
        {"field": "max_z", "type": QuillType.FLOAT, "description": "max z"},
    ]


class QuillVertexObject(QuillObject):
    TYPE = QuillType.VERTEX
    VALUE_OFFSETS = [
        {"field": "position", "type": QuillType.VEC3, "description": "Position"},
        {"field": "normal", "type": QuillType.VEC3, "description": "Normal"},
        {"field": "tangent", "type": QuillType.VEC3, "description": "Tangent"},
        {"field": "color", "type": QuillType.VEC3, "description": "Color"},
        {"field": "opacity", "type": QuillType.FLOAT, "description": "Opacity"},
        {"field": "width", "type": QuillType.FLOAT, "description": "Width"},
    ]


class QuillVec3Object(QuillObject):
    TYPE = QuillType.VEC3
    VALUE_OFFSETS = [
        {"field": "x", "type": QuillType.FLOAT, "description": "X"},
        {"field": "y", "type": QuillType.FLOAT, "description": "Y"},
        {"field": "z", "type": QuillType.FLOAT, "description": "Z"},
    ]

class QuillPixelRGBAObject(QuillObject):
    TYPE = QuillType.RGBA
    VALUE_OFFSETS = [
        {"field": "r", "type": QuillType.CHAR, "description": "R"},
        {"field": "g", "type": QuillType.CHAR, "description": "G"},
        {"field": "b", "type": QuillType.CHAR, "description": "B"},
        {"field": "a", "type": QuillType.CHAR, "description": "A"},
    ]


class QuillPixelRGBObject(QuillObject):
    TYPE = QuillType.RGB
    VALUE_OFFSETS = [
        {"field": "r", "type": QuillType.CHAR, "description": "R"},
        {"field": "g", "type": QuillType.CHAR, "description": "G"},
        {"field": "b", "type": QuillType.CHAR, "description": "B"},
    ]


class QuillPictureObject(QuillObject):

    TYPE = QuillType.PICTURE

    HEADER_OFFSETS = [
        {"field": "unknown0", "type": QuillType.INT16, "description": ""},
        {"field": "pixel_channel_size", "type": QuillType.INT16, "description": "Pixel channel size"},
        {"field": "unknown1", "type": QuillType.CHAR, "description": ""},
        {"field": "image_type", "type": QuillType.CHAR, "description": "Possibly an image type"},
        {"field": "unknown2", "type": QuillType.CHAR, "description": ""},
        {"field": "unknown3", "type": QuillType.CHAR, "description": ""},
        {"field": "image_width", "type": QuillType.INT32, "description": "Width of image"},
        {"field": "image_height", "type": QuillType.INT32, "description": "Height of image"},
        {"field": "unknown4", "type": QuillType.CHAR, "description": ""},
        {"field": "unknown5", "type": QuillType.CHAR, "description": ""},
        {"field": "unknown6", "type": QuillType.CHAR, "description": ""},
        {"field": "unknown7", "type": QuillType.CHAR, "description": ""},
    ]
    VALUE_OFFSETS = [
        # Picture pixel type are unknown at instantiation
        {"field": "pixels", "type": None, "sequence": True, "description": ""},
    ]

    def get_pixel_type(self):
        if self.image_type == 6:
            return QuillType.RGB
        elif self.image_type == 7:
            return QuillType.RGBA
        else:
            return None

    @classmethod
    def decode_image(cls, binary_chunk_obj, image_width, image_height, num_channels):
        size = int(image_width * image_height * num_channels)
        pixel_data = np.frombuffer(binary_chunk_obj.get_data(), dtype=np.uint8)
        # PIL takes in image data in (image_height, image_width, num_channels)
        image_data = pixel_data.reshape(image_height, image_width, num_channels)
        image = Image.fromarray(image_data)
        return image


    @classmethod
    def save_image(cls, image, image_path):
        image_path = os.path.join("")
        image.save(image_path)
        return image_path

    def decode_values(self, binary_data_obj):
        pixel_sequence_length = self.image_width * self.image_height
        pixel_type = self.get_pixel_type()
        binary_chunk_obj, _ = binary_data_obj.chunk(0, pixel_sequence_length * pixel_type.size)
        image = self.decode_image(
            binary_chunk_obj,
            self.image_width,
            self.image_height,
            pixel_type.size,
        )
        self.values.append(image)

class QuillSceneData(object):
    def __init__(self, data):
        self.data = data
        self.files = {}

    def get_data(self):
        return self.data

    def generate_drawing_offset(self, offset):
        return {"field": "drawing", "offset": offset, "type": QuillType.DRAWING, "description": "Drawing"}

    def generate_picture_offset(self, offset):
        return {"field": "picture", "offset": offset, "type": QuillType.PICTURE, "description": "Picture"}

    def get_layer_value_offsets(self, layer_data, layer_path):
        child_layers = layer_data["Implementation"]["Children"]
        quill_file_value_offsets = []
        for child_layer in child_layers:
            child_layer_path = os.path.join(layer_path, child_layer["Name"])
            if child_layer["Type"] == "Paint":
                for drawing in child_layer["Implementation"]["Drawings"]:
                    offset = bytes.fromhex(drawing["DataFileOffset"])
                    offset = int(drawing["DataFileOffset"], 16)
                    self.files[offset] = {"path": child_layer_path}
                    quill_file_value_offsets.append(self.generate_drawing_offset(offset))
            elif child_layer["Type"] == "Picture":
                offset = bytes.fromhex(child_layer["Implementation"]["DataFileOffset"])
                offset = int(child_layer["Implementation"]["DataFileOffset"], 16)
                self.files[offset] = {"path": child_layer_path}
                quill_file_value_offsets.append(self.generate_picture_offset(offset))
        return quill_file_value_offsets

    def get_quill_file_value_offsets(self):
        root_layer_data = self.data["Sequence"]["RootLayer"]
        quill_file_value_offsets = self.get_layer_value_offsets(root_layer_data, root_layer_data["Name"])
        return quill_file_value_offsets


class QuillPrimitiveObject(QuillObject):
    TYPE = None


class QuillBinaryData(object):
    def __init__(self, binary_data):
        self.binary_data = binary_data

    def get_data(self):
        return self.binary_data

    def chunk(self, offset, size=None):
        if size is None:
            size = self.get_size() - offset
        binary_chunk = self.binary_data[offset:offset+size]
        new_offset = offset + size
        return QuillBinaryData(binary_chunk), new_offset

    def get_size(self):
        return len(self.binary_data)


class QuillScene(object):
    def __init__(self, scene_data_obj, quill_scene_obj):
        self.scene_data_obj = scene_data_obj
        self.quill_scene_obj = quill_scene_obj

class QuillProject(object):
    def __init__(self, proj_dir):

        input_state_json_path = os.path.join(proj_dir, 'State.json')
        if not os.path.exists(input_state_json_path):
            input_state_json_path = os.path.join(proj_dir, '~State.json')
        with open(input_state_json_path, 'r') as json_file:
            self.state_data = json.load(json_file)

        input_quill_json_path = os.path.join(proj_dir, 'Quill.json')
        with open(input_quill_json_path, 'r') as json_file:
            scene_data = json.load(json_file)
        scene_data_obj = QuillSceneData(scene_data)
        input_quill_qbin_path = os.path.join(proj_dir, 'Quill.qbin')
        with open(input_quill_qbin_path, 'rb') as binary_file:
            binary_data = binary_file.read()
        binary_data_obj = QuillBinaryData(binary_data)

        # State data is not necessary to decode
        self.quill_scene = QuillBinaryDecoder(binary_data_obj, scene_data_obj).run()

    def write(self, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Write both
        # self.write_quill_binary(output_dir)
        self.write_quill_ascii(output_dir)

        state_json_path = os.path.join(output_dir, 'State.json')
        with open(state_json_path, 'w') as outfile:
            json.dump(self.state_data, outfile, indent=1)

    def write_quill_binary(self, output_dir):
        binary_data_obj, scene_data_obj = QuillBinaryEncoder(self.quill_scene).run()
        quill_json_path = os.path.join(output_dir, 'Quill.json')
        with open(quill_json_path, 'w') as outfile:
            json.dump(scene_data_obj.get_data(), outfile, indent=1)
        quill_qbin_path = os.path.join(output_dir, 'Quill.qbin')
        with open(quill_qbin_path, 'wb') as binary_file:
            binary_file.write(binary_data_obj.get_data())

    def write_images(self, output_dir):
        print(self.quill_scene.scene_data_obj.images)

    def write_quill_ascii(self, output_dir):
        quill_json = QuillJsonEncoder(self.quill_scene).run()
        quill_qa_path = os.path.join(output_dir, 'Quill.qa')
        with open(quill_qa_path, 'w') as outfile:
            json.dump(quill_json, outfile, indent=1)


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
