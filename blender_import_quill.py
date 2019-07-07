import bpy
import os
import sys


def read_args():
	argv = sys.argv
	argv = argv[argv.index("--") + 1:]
	abc_filepath = os.path.abspath(argv[0])
	if len(argv) > 1:
		background_color_name = argv[1]
	else:
		background_color_name = 'BgRGB'

	return abc_filepath, background_color_name


def clear_scene():
	bpy.ops.object.select_all(action='SELECT')
	bpy.ops.object.delete(use_global=False)


def import_quill(abc_filepath):
	bpy.ops.wm.alembic_import(filepath=abc_filepath, as_background_job=False)
	return bpy.data.objects["Root"]


def create_flat_material():
	flat_mat = bpy.data.materials.new(name="FlatQuillMaterial") #set new material to variable
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


def set_background_color_from_obj(background_color_name):
	bg_obj = bpy.data.objects[background_color_name]
	vcol = bg_obj.data.vertex_colors[0]
	# Gamma correct
	r,g,b,_ = [channel ** 2.2 for channel in vcol.data[0].color]
	background_node = bpy.data.worlds['World'].node_tree.nodes['Background']
	background_node.inputs['Color'].default_value = (r,g,b, 1.0)
	bpy.ops.object.select_all(action='DESELECT')
	bg_obj.select_set(True)
	bpy.ops.object.delete()


def main():
	abc_filepath, background_color_name = read_args()
	clear_scene()
	root_obj = import_quill(abc_filepath)
	flat_mat = create_flat_material()
	apply_material_to_quill_layers(root_obj, flat_mat)
	set_background_color_from_obj(background_color_name)

main()