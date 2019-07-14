import bpy
import os
import sys


def read_args():
    import argparse, sys

    # Getting the arguments past the blender input
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]

    parser = argparse.ArgumentParser()

    background_group = parser.add_mutually_exclusive_group()
    background_group.add_argument(
        '--background-name',
        help='The name of an object in the Quill scene to reference the background color',
        type=str,
        default=None,
    )
    background_group.add_argument(
        '--background-color',
        help='The HEX color of the background (in the form FFAA00)',
        type=str,
        default=None,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--alembic',
        help='Path to the .abc file to import',
        type=str,
    )
    input_group.add_argument(
        '--quill',
        help='Path to the input Quill project folder',
        type=str,
    )

    args = parser.parse_args(argv)
    return args


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def set_view_settings():
    bpy.data.scenes['Scene'].view_settings.view_transform = 'Standard'


def import_alembic(abc_filepath):
    import os
    abc_filepath = os.path.abspath(abc_filepath)
    bpy.ops.wm.alembic_import(filepath=abc_filepath, as_background_job=False)
    return bpy.data.objects["Root"]


def create_flat_material():
    flat_mat = bpy.data.materials.new(name="FlatMaterial") #set new material to variable
    flat_mat.use_nodes = True
    nodes = flat_mat.node_tree.nodes
    links = flat_mat.node_tree.links
    attribute_node = nodes.new('ShaderNodeAttribute')
    attribute_node.attribute_name = 'rgba'
    output_node = nodes['Material Output']
    links.new(attribute_node.outputs["Color"], output_node.inputs['Surface'])
    return flat_mat


def apply_material_to_quill_layers(obj, mat):
    if obj.type == 'EMPTY':
        for child_obj in obj.children:
            apply_material_to_quill_layers(child_obj, mat)
    elif obj.type == 'MESH':
        obj.active_material = mat
    else:
        return


def set_background_color_from_obj(background_color_name, gamma_correct=True):
    bg_obj = bpy.data.objects[background_color_name]
    vcol = bg_obj.data.vertex_colors[0]
    r,g,b,_ = vcol.data[0].color
    if gamma_correct:
        r,g,b = [channel ** 2.2 for channel in (r,g,b)]
    background_node = bpy.data.worlds['World'].node_tree.nodes['Background']
    background_node.inputs['Color'].default_value = (r,g,b, 1.0)
    bpy.ops.object.select_all(action='DESELECT')
    bg_obj.select_set(True)
    bpy.ops.object.delete()


def main():
    args = read_args()

    clear_scene()
    set_view_settings()
    if args.alembic:
        root_obj = import_alembic(args.alembic)
        flat_mat = create_flat_material()
        apply_material_to_quill_layers(root_obj, flat_mat)
    if args.background_name:
        set_background_color_from_obj(args.background_name)

main()