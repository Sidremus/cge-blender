# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# This script exports from Blender to castle-anim-frames format,
# which stands for "Castle Game Engine's Animation Frames".
# The format specification is on
# https://castle-engine.io/castle_animation_frames.php
# Each still frame is exported to a static frame (as X3D or glTF).
# We call actual Blender X3D/glTF exporter to do this.
#
# The latest version of this script can be found on
# https://castle-engine.io/creating_data_blender.php

bl_info = {
    "name": "Export Castle Animation Frames",
    "description": "Export animation to Castle Game Engine's Animation Frames format.",
    "author": "Michalis Kamburelis",
    "version": (2, 0),
    "blender": (2, 80, 0),
    "location": "File > Export > Castle Animation Frames (.castle-anim-frames)",
    "warning": "", # used for warning icon and text in addons panel
    # Note: this should only lead to official Blender wiki.
    # But since this script (probably) will not be official part of Blender,
    # we can overuse it. Normal "link:" item is not visible in addons window.
    "wiki_url": "https://castle-engine.io/creating_data_blender.php",
    "link": "https://castle-engine.io/creating_data_blender.php",
    "category": "Import-Export"}

import bpy
import os
from bpy_extras.io_utils import (
    orientation_helper,
    path_reference_mode,
    axis_conversion,
    )
from bpy.props import *
from mathutils import Vector
import addon_utils

@orientation_helper(axis_forward='Z', axis_up='Y')
class ExportCastleAnimFrames(bpy.types.Operator):
    """Export the animation to Castle Animation Frames (castle-anim-frames) format"""
    bl_idname = "export.castle_anim_frames"
    bl_label = "Castle Animation Frames (.castle-anim-frames)"

    # ------------------------------------------------------------------------
    # properties for interaction with fileselect_add

    filepath: StringProperty(subtype="FILE_PATH")
    # for some reason,
    # filter "*.castle-anim-frames" doesn't work correctly (hides all files),
    # so use "*.castle*"
    filter_glob: StringProperty(default="*.castle*", options={'HIDDEN'})

    # ------------------------------------------------------------------------
    # properties special for castle-anim-frames export

    frame_skip: IntProperty(name="Frames to skip",
        # As part of exporting to castle-anim-frames, we export each still
        # frame to another format. We iterate over all animation frames, from the start,
        # exporting it and skipping this number of following frames.
        # Smaller values mean less files (less disk usage, faster animation
        # loading in game) but also worse quality (as castle-anim-frames loader in game
        # only interpolates linearly between frames). Default is 4, which
        # means every 5th frame is exported, which means 5 frames for each
        # second (for default 25fps)
        description="How many frames to skip between the exported frames. The Castle Game Engine using castle-anim-frames format will reconstruct these frames using linear interpolation.",
            default=4, min=0, max=50)

    actions_object: StringProperty(
            name="Actions",
            description="If set, we will export all the actions of a given object. Leave empty to instead export the current animation from Start to End.",
            default='',
            )

    make_duplicates_real: BoolProperty(
            name="Make Duplicates Real",
            description="This option allows to export particles (and other things not exportable without a \"Make Duplicates Real\" call).",
            default=False,
            )

    frame_format: EnumProperty(
        name='Format',
        items=(('GLTF', 'glTF',
                'Export each static frame using glTF exporter. This is more functional in general, as glTF exporter can handle normal maps, PBR materials, unlit materials etc.'),
               ('X3D', 'X3D',
                'Export each static frame using X3D exporter. This is less functional in general, as current X3D exporter misses various features.')),
        description=(
            'Each static frame is recorded using another exporter, to X3D or glTF.'
        ),
        default='GLTF'
    )

    # ------------------------------------------------------------------------
    # properies passed through to the X3D/glTF exporter,
    # definition copied from io_scene_x3d/__init__.py

    # TODO: remove most of these, keep only ones that make sense for both X3D and glTF.
    # TODO: axis convert into simple boolean "Y Up?".

    use_selection: BoolProperty(
            name="Selection Only",
            description="Export selected objects only",
            default=False,
            )
    use_mesh_modifiers: BoolProperty(
            name="Apply Modifiers",
            description="Use transformed mesh data from each object",
            default=True,
            )
    use_triangulate: BoolProperty(
            name="Triangulate",
            description="Write quads into 'IndexedTriangleSet'",
            default=False,
            )
    use_normals: BoolProperty(
            name="Normals",
            description="Write normals with geometry",
            default=False,
            )
    use_hierarchy: BoolProperty(
            name="Hierarchy",
            description="Export parent child relationships",
            default=True,
            )
    name_decorations: BoolProperty(
            name="Name decorations",
            description=("Add prefixes to the names of exported nodes to "
                         "indicate their type"),
            default=True,
            )
    use_h3d: BoolProperty(
            name="H3D Extensions",
            description="Export shaders for H3D",
            default=False,
            )

    path_mode: path_reference_mode

    # methods ----------------------------------------------------------------

    def draw(self, context):
        # custom drawn operator,
        # see https://www.blender.org/api/blender_python_api_2_57_release/bpy.types.Operator.html
        layout = self.layout

        box = layout.box()
        box.label(text="Animation settings:")

        # use prop_search to select an object,
        # see http://blender.stackexchange.com/questions/7973/object-selection-box-in-addon
        # https://www.blender.org/api/blender_python_api_2_70_release/bpy.types.UILayout.html#bpy.types.UILayout.prop_search
        # https://blenderartists.org/forum/showthread.php?200311-Creating-a-Object-Selection-Box-in-Panel-UI-of-Blender-2-5
        # http://blender.stackexchange.com/questions/6975/is-it-possible-to-use-bpy-props-pointerproperty-to-store-a-pointer-to-an-object
        box.prop_search(self, 'actions_object', context.scene, "objects")

        box.prop(self, "frame_skip")
        box.prop(self, "make_duplicates_real")
        box.prop(self, "frame_format")

        box = layout.box()
        box.label(text="X3D settings:")
        box.prop(self, "use_selection")
        box.prop(self, "use_mesh_modifiers")
        box.prop(self, "use_triangulate")
        box.prop(self, "use_normals")
        box.prop(self, "use_hierarchy")
        box.prop(self, "name_decorations")
        box.prop(self, "use_h3d")
        box.prop(self, "axis_forward")
        box.prop(self, "axis_up")
        box.prop(self, "path_mode")

    def is_bound_box_empty(self, bound_box):
        """Is the Blender bound_box empty.

        The box is represented as 24 floats, as defined by Blender API, see
        https://www.blender.org/api/blender_python_api_current/bpy.types.Object.html#bpy.types.Object.bound_box
        (somewhat uncomfortable representation, IMHO...).
        """

        for f in bound_box:
            if f != -1:
                return False
        return True

    def get_current_bounding_box(self, context):
        """Calculate current scene bounding box.
        Returns two 3D vectors, bounding box center and size.

        If the box is empty, the center is (0, 0, 0) and size is (-1, -1, -1).
        This is consistent with X3D Group node bboxCenter/Size
        (see http://www.web3d.org/documents/specifications/19775-1/V3.2/Part01/components/group.html#Group)
        and castle-anim-frames bounding_box_center/size fields
        (see http://michalis.ii.uni.wroc.pl/cge-www-preview/castle_animation_frames.php).
        """

        view_layer = context.view_layer
        scene_box_empty = True
        scene_box_min = (0.0, 0.0, 0.0)
        scene_box_max = (0.0, 0.0, 0.0)

        if self.use_selection:
            objects = [obj for obj in context.scene.objects if obj.visible_get(view_layer=view_layer) and obj.select_get(view_layer=view_layer)]
        else:
            objects = [obj for obj in context.scene.objects if obj.visible_get(view_layer=view_layer)]

        global_matrix = axis_conversion(to_forward=self.axis_forward, to_up=self.axis_up).to_4x4()

        for ob in objects:
            # filter out cameras, lights etc., otherwise they have a bounding box
            if (ob.type not in ('ARMATURE', 'LATTICE', 'EMPTY', 'CAMERA', 'LAMP', 'SPEAKER')) and \
               (not self.is_bound_box_empty(ob.bound_box)):
                # world-space bounding box calculation,
                # see blender/2.78/scripts/addons/object_fracture_cell/fracture_cell_setup.py
                # and http://blender.stackexchange.com/questions/8459/get-blender-x-y-z-and-bounding-box-with-script
                object_box_points = [global_matrix @ ob.matrix_world @ Vector(corner) for corner in ob.bound_box]

                # calculate object_box_min/max
                object_box_min = (object_box_points[0].x, object_box_points[0].y,  object_box_points[0].z)
                object_box_max = object_box_min
                for v in object_box_points:
                    object_box_min = (min(v.x, object_box_min[0]),
                                      min(v.y, object_box_min[1]),
                                      min(v.z, object_box_min[2]))
                    object_box_max = (max(v.x, object_box_max[0]),
                                      max(v.y, object_box_max[1]),
                                      max(v.z, object_box_max[2]))

                # update scene_box_min/max/empty
                if scene_box_empty:
                    scene_box_min = object_box_min
                    scene_box_max = object_box_max
                else:
                    scene_box_min = (min(scene_box_min[0], object_box_min[0]),
                                     min(scene_box_min[1], object_box_min[1]),
                                     min(scene_box_min[2], object_box_min[2]))
                    scene_box_max = (max(scene_box_max[0], object_box_max[0]),
                                     max(scene_box_max[1], object_box_max[1]),
                                     max(scene_box_max[2], object_box_max[2]))
                scene_box_empty = False

        # calculate scene_box_center/size from scene_box_min/max/empty
        if scene_box_empty:
            scene_box_center = (0.0, 0.0, 0.0)
            scene_box_size = (-1.0, -1.0, -1.0)
        else:
            scene_box_center = ((scene_box_min[0] + scene_box_max[0]) / 2.0,
                                (scene_box_min[1] + scene_box_max[1]) / 2.0,
                                (scene_box_min[2] + scene_box_max[2]) / 2.0)
            scene_box_size = (scene_box_max[0] - scene_box_min[0],
                              scene_box_max[1] - scene_box_min[1],
                              scene_box_max[2] - scene_box_min[2])

        return (scene_box_center, scene_box_size)

    def fix_scene_before_x3d_export(self, context):
        """Fix the Blender scene before exporting.

        Blender 2.8 has a weird bug: running bpy.ops.export_scene.x3d
        one after another (which is normal for this script), the export process
        will think that some materials have already been written
        (and will use <Material USE="XXX" /> instead of <Material DEF="XXX" diffuseColor="..." ... />).
        This occurs only when mesh is obtained by to_mesh().
        It seems that Blender cashes this mesh (even despite calling to_mesh_clear()
        in export_x3d.py) and also materials (or at least tags?) are copied
        (instead of being only references to same things as in bpy.data.materials).
        In effect the material.tag values are retained across many
        bpy.ops.export_scene.x3d calls, and even bpy.data.materials.tag(False)
        doesn't help to reset them.
        """

        depsgraph = context.evaluated_depsgraph_get()
        for obj in bpy.data.objects:
            uses_temporary_mesh = False
            # The logic when to set uses_temporary_mesh follows X3D exporter
            if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
                if (obj.type != 'MESH') or (self.use_mesh_modifiers and obj.is_modified(context.scene, 'PREVIEW')):
                    uses_temporary_mesh = True
            if uses_temporary_mesh:
                obj_for_mesh = obj.evaluated_get(depsgraph) if self.use_mesh_modifiers else obj
                mesh = obj_for_mesh.to_mesh()
                for mat in mesh.materials:
                    if mat.tag:
                        print("Workarounding Blender 2.8 bug with materials tag not reset for %s" % mat.name)
                        mat.tag = False
                obj.to_mesh_clear()

    def output_frame_x3d(self, context, output_file):
        """Append a given frame to output_file in X3D format."""

        # calculate filenames stuff
        (output_dir, output_basename) = os.path.split(self.filepath)
        temp_file_name = os.path.join(output_dir, os.path.splitext(output_basename)[0] + "_tmp.x3d")

        self.fix_scene_before_x3d_export(context)

        # write X3D with animation frame
        bpy.ops.export_scene.x3d(filepath=temp_file_name,
            check_existing = False,
            use_compress = False, # never compress
            # pass through our properties to X3D exporter
            use_selection              = self.use_selection,
            use_mesh_modifiers         = self.use_mesh_modifiers,
            use_triangulate            = self.use_triangulate,
            use_normals                = self.use_normals,
            use_hierarchy              = self.use_hierarchy,
            name_decorations           = self.name_decorations,
            use_h3d                    = self.use_h3d,
            axis_forward               = self.axis_forward,
            axis_up                    = self.axis_up,
            path_mode                  = self.path_mode)

        # read from temporary X3D file, and remove it
        with open(temp_file_name, 'r') as temp_contents_file:
            temp_contents = temp_contents_file.read()
        os.remove(temp_file_name)

        # add X3D content
        temp_contents = temp_contents.replace('<?xml version="1.0" encoding="UTF-8"?>', '')
        temp_contents = temp_contents.replace('<!DOCTYPE X3D PUBLIC "ISO//Web3D//DTD X3D 3.0//EN" "http://www.web3d.org/specifications/x3d-3.0.dtd">', '')
        output_file.write(temp_contents)

    def output_frame_gltf(self, context, output_file):
        """Append a given frame to output_file in glTF format."""

        # Note that using glb would be more efficient,
        # but then textures are embedded too in every frame, which are not useful.

        # calculate filenames stuff
        (output_dir, output_basename) = os.path.split(self.filepath)
        temp_file_name = os.path.join(output_dir, os.path.splitext(output_basename)[0] + "_tmp.gltf")

        bpy.ops.export_scene.gltf(filepath=temp_file_name,
            export_format = 'GLTF_EMBEDDED',
            check_existing = False,
            export_lights = True,
            export_apply = self.use_mesh_modifiers,
            export_extras = True,
            export_cameras = True,
            export_selected = self.use_selection,
            # TODO: export_yup = self.export_yup,

            # Note to below settings:
            # we will animate the whole castle-anim-frames, no need to export animation inside glTF.
            export_current_frame = True,
            export_animations = False,
            # export_skins = False, # unfortunately disabling skins causes bugs in glTF exporter on armature
            export_morph = False,
            export_morph_normal = False,
            export_nla_strips = False,
            export_force_sampling = False
            )

        # read from temporary glTF file, and remove it
        with open(temp_file_name, 'r') as temp_contents_file:
            temp_contents = temp_contents_file.read()
        os.remove(temp_file_name)

        # add glTF content (TODO: escape XML special chars)
        output_file.write(temp_contents)

    def output_frame(self, context, output_file, frame, frame_start):
        """Output a given frame to a single file, and add <frame...> line to
        castle-anim-frames file.

        Arguments:
        output_file   -- the handle to write xxx.castle-anim-frames file,
                         to add <frame...> line.
        frame         -- current frame number.
        frame_start   -- the start frame number, used to shift frame times
                         such that castle-anim-frames animation starts from time = 0.0.
        """

        # set the animation frame (before calculating bounding box
        # and making duplicates real)
        context.scene.frame_set(frame)

        if self.make_duplicates_real:
            self.make_duplicates_real_before(context)

        # calculate bounding box in world space
        (bounding_box_center, bounding_box_size) = self.get_current_bounding_box(context)

        if self.frame_format == 'GLTF':
            mime_type = 'model/gltf+json'
        else:
            mime_type = 'model/x3d+vrml'

        # write castle-anim-frames line
        output_file.write('\t\t<frame time="%f" mime_type="%s" bounding_box_center="%f %f %f" bounding_box_size="%f %f %f">\n' %
          ((frame-frame_start) / 25.0,
           mime_type,
           bounding_box_center[0], bounding_box_center[1], bounding_box_center[2],
           bounding_box_size  [0], bounding_box_size  [1], bounding_box_size  [2]))

        if self.frame_format == 'GLTF':
            self.output_frame_gltf(context, output_file)
        else:
            self.output_frame_x3d(context, output_file)

        output_file.write('\n\t\t</frame>\n')

        if self.make_duplicates_real:
            self.make_duplicates_real_after(context)

    # Export a single animation (e.g. coming from a single action in Blender)
    # to an <animation> element in castle-anim-frames.
    #
    # animation_name must be a string.
    #
    # frame_start, frame_end must be integer.
    def output_one_animation(self, context, output_file, animation_name, frame_start, frame_end):
        if animation_name != '':
            output_file.write('\t<animation name="' + animation_name + '">\n')
        else:
            output_file.write('\t<animation>\n')

        frame = frame_start
        while frame < frame_end:
            self.output_frame(context, output_file, frame, frame_start)
            frame += 1 + self.frame_skip
        # the last frame should be always output, regardless if we would "hit"
        # it with given frame_skip.
        self.output_frame(context, output_file, frame_end, frame_start)

        output_file.write('\t</animation>\n')


    def execute(self, context):
        output_file = open(self.filepath, 'w')
        output_file.write('<?xml version="1.0"?>\n')
        output_file.write('<animations>\n')

        if self.actions_object != '':
            actions_object_o = context.scene.objects[self.actions_object]

            # first get actions_to_export,
            # otherwise when we change the actions_object_o.animation_data.action,
            # an old action may be temporarily considered unused
            actions_to_export = []
            for action in bpy.data.actions:
                # Use user_of_id to determine actions belonging to this object.
                #
                # It seems it fails to detect usage sometimes (see
                # https://sourceforge.net/p/castle-engine/discussion/general/thread/902a6753/?limit=25#392c),
                # and reverse ("action.user_of_id(actions_object_o)") doesn't help,
                # so just always add all actions with "use_fake_user".
                if actions_object_o.user_of_id(action) or action.use_fake_user:
                    actions_to_export.append(action)

            if len(actions_to_export) > 0:
                original_action = actions_object_o.animation_data.action
                try:
                    for action in actions_to_export:
                        act_start, act_end = action.frame_range
                        act_start = int(act_start)
                        act_end = int(act_end)
                        actions_object_o.animation_data.action = action
                        print("Exporting action", action.name, "with frames" , act_start, "-", act_end)
                        self.output_one_animation(context, output_file, action.name, act_start, act_end)
                finally:
                    # without restoring this, the action selected previously
                    # would be lost, with 0 users
                    actions_object_o.animation_data.action = original_action
            else:
                raise Exception('No action found on object "' + self.actions_object + '"')
        else:
            # if no actions to use, then export whole context.scene.frame_start..end
            print("Exporting animation with frames" , context.scene.frame_start, "-", context.scene.frame_end)
            self.output_one_animation(context, output_file, "animation", context.scene.frame_start, context.scene.frame_end)

        output_file.write('</animations>\n')
        output_file.close()

        return {'FINISHED'}

    # Calculate the default object from which we should take actions.
    # Returns string (object mame, or '' if not found).
    def get_default_actions_object(self, context):
        view_layer = context.view_layer
        if self.use_selection:
            objects = [obj for obj in context.scene.objects if obj.visible_get(view_layer=view_layer) and obj.select_get(view_layer=view_layer)]
        else:
            objects = [obj for obj in context.scene.objects if obj.visible_get(view_layer=view_layer)]
        more_than_one_armature = False
        armature = None
        for ob in objects:
            if ob.type == 'ARMATURE' and ob.animation_data:
                if armature != None:
                    more_than_one_armature = True
                armature = ob
        if (armature != None) and (not more_than_one_armature):
            return armature.name
        else:
            if more_than_one_armature:
                print("Multiple armatures in the scene, cannot determine which one to use for \"Actions\" to export to castle-anim-frames. Adjust the \"Actions\" setting as needed.")
            return ''

    def invoke(self, context, event):
        # set self.filepath (will be used by fileselect_add)
        # just like bpy_extras/io_utils.py
        if not self.filepath:
            blend_filepath = context.blend_data.filepath
            if not blend_filepath:
                blend_filepath = "untitled"
            else:
                blend_filepath = os.path.splitext(blend_filepath)[0]

            self.filepath = blend_filepath + ".castle-anim-frames"

        # initialize actions_object
        self.actions_object = self.get_default_actions_object(context)

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def make_duplicates_real_before(self, context):
        self.old_objects = list(context.scene.objects)
        self.old_objects_len = len(self.old_objects)

        # Not sure what do I need to override for duplicates_make_real.
        # Note: Don't override selected_editable_bases! It will crash Blender!
        # override = {\
        #   'selected_objects': self.old_objects,\
        #   'selected_editable_objects': self.old_objects,\
        #   'selected_bases': self.old_objects}
        # bpy.ops.object.duplicates_make_real(override)

        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.duplicates_make_real()

        # Hm, I cannot seem to be able to undo the duplicates_make_real effect easily.
        # Doing
        #   bpy.ops.ed.undo()
        # after
        #   bpy.ops.object.duplicates_make_real(override, 'EXEC_DEFAULT', True)
        # doesn't work.
        # See https://www.blender.org/api/blender_python_api_2_63_14/bpy.ops.html
        # about undo parameter. For some reason notes removed in later versions,
        # see https://www.blender.org/api/blender_python_api_current/bpy.ops.html .
        # Doing
        #   bpy.ops.ed.undo_push()
        # also doesn't help.

    def make_duplicates_real_after(self, context):
        new_objects = list(context.scene.objects)
        new_objects_len = len(new_objects)

        if new_objects_len < self.old_objects_len:
            # TODO: raise something more specific, what other scripts do?
            raise Exception("Error: we have less objecs after running duplicates_make_real, submit a bug")

        duplicated_objects = [item for item in new_objects if item not in self.old_objects]

        if len(duplicated_objects) != 0:
            print("Make Duplicates Real Created new objects:", len(duplicated_objects))

            # Crashes...
            # override = {\
            #   'selected_objects': duplicated_objects,\
            #   'selected_editable_objects': duplicated_objects,\
            #   'selected_bases': duplicated_objects}
            # bpy.ops.object.delete(override)

            selected_count = 0
            for ob in context.scene.objects:
                ob.select_set((ob in new_objects) and (ob not in self.old_objects))
                if ob.select_get():
                    selected_count = selected_count + 1
            if selected_count != len(duplicated_objects):
                raise Exception("Error: we did not select as many as expected, submit a bug")

            bpy.ops.object.delete()

        final_objects_len = len(list(context.scene.objects))
        if final_objects_len != self.old_objects_len:
            raise Exception("At the end, we do not have as many objects as at the beginning: ", self.old_objects_len, " -> ", new_objects_len, " -> ", final_objects_len)

        #print("Done making duplicates real: ", self.old_objects_len, " -> ", new_objects_len, " -> ", final_objects_len)

def menu_func(self, context):
    self.layout.operator_context = 'INVOKE_DEFAULT'
    self.layout.operator(ExportCastleAnimFrames.bl_idname, text=ExportCastleAnimFrames.bl_label)

def register():
    bpy.utils.register_class(ExportCastleAnimFrames)
    bpy.types.TOPBAR_MT_file_export.append(menu_func)

def unregister():
    bpy.utils.unregister_class(ExportCastleAnimFrames)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func)

if __name__ == "__main__":
    register()
    bpy.ops.export.castle_anim_frames('INVOKE_DEFAULT')
