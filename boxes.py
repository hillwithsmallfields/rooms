#!/usr/bin/env python3

import argparse
import csv

import rgbcolour

PREAMBLE0 = """
// Generated by https://github.com/hillwithsmallfields/boxes/blob/trunk/boxes.py

wall_thickness = %g;
floor_thickness = %g;
ceiling_thickness = %g;

module hole(preshift, rot, postshift, dimensions, label) {
    translate(preshift) rotate(rot) translate(postshift) cube(dimensions);
}

module box(position, dimensions, colour, label) {
    color(colour) {
        translate(position) {
            // make this hollow by subtracting an inner cuboid
            difference() {
                cube(dimensions);
                translate([wall_thickness/2, wall_thickness/2, floor_thickness]) {
                    cube([dimensions[0]-wall_thickness, dimensions[1]-wall_thickness, dimensions[2]-floor_thickness]);
                }
                children();
            }
        }
    }
}
"""
PREAMBLE1 = """
difference() {
  union() {
"""
PREAMBLE1DEBUG = """
union() {
"""

INTERAMBLE = """  }
  union() {
"""

INTERAMBLEDEBUG = """  }
color("red") union() {
"""

POSTAMBLE = """  }
}
"""

POSTAMBLEDEBUG = """  }
"""

# scratch = """
# box([0.0, 0.0, 0.0], [435.0, 385.0, 253.0], 1, "Living room") {
#      wallrotate = 90;
#      fromwall = 90;
#      fromfloor = 70;
#      width = 245;
#      height = 135;
#      rotate([0, 0, wallrotate]) {
#           translate([fromwall, -10, fromfloor]) {
#           cube([width, 20, height]);
#           }
#      }
# };
# """

# The __init__ methods for all the things we read from the CSV files
# each take the whole CSV row as their input.

class Box:

    """A cuboid positive space, such as a room, box, or shelf and the space it supports.
    Not a hole such as a door or window."""

    pass

    def __init__(self, data, opacity=1.0):
        self.box_type = data.get('type', 'room')
        self.name = data.get('name')
        self.dimensions = [float(data.get('width')),
                           float(data.get('depth')),
                           float(data.get('height'))]
        self.position = [0.0, 0.0, 0.0]
        self.adjacent = data.get('adjacent')
        self.direction = data.get('direction')
        self.alignment = data.get('alignment')
        self.offset = data.get('offset', 0.0) or 0.0
        self.holes = []
        self.neighbours = {'left': [],
                           'right': [],
                           'front': [],
                           'behind': []}
        self.colour = data.get('colour', [.5, .5, .5, .5])
        if self.colour == "":
            self.colour = [.5, .5, .5, .5]
        if isinstance(self.colour, str):
            self.colour = rgbcolour.rgbcolour(self.colour, opacity)

    def __str__(self):
        return "<box %s of size %s at %s to %s of %s, %s-aligned>" % (
            self.name,
            self.dimensions,
            self.position,
            self.direction, self.adjacent, self.alignment)

    def write_scad(self, stream):
        """Write the SCAD code for this box.
        Return a string describing the holes attached the box."""
        stream.write("""    box(%s, %s, %s, "%s");\n""" % (
            self.position,
            self.dimensions,
            ('"%s"' % self.colour) if isinstance(self.colour, str) else self.colour,
            self.name))
        return "".join(hole.scad_string(self)
                       for hole in self.holes)

def cell_as_float(row, name):
    """Convert the contents of a spreadsheet cell to a float.
    Empty cells are treated as 0.0"""
    value = row.get(name)
    return 0 if value in (None, "") else float(value)

class Hole:

    """A cuboid negative space to punch out of the wall of a box such as room.
    This represents doors and windows."""

    pass

    def __init__(self, data):
        self.name = data['name']
        self.dimensions = [float(data.get('width')),  # from one side of the hole to the other
                           float(data.get('depth')),  # from bottom to top of the hole
                           40]                        # fill in the thickness of the hole later
        # the room that this hole is in one of the walls of:
        self.adjacent = data.get('adjacent')
        # which wall the hole is in (front, left, back, right):
        self.direction = data.get('direction')
        # from the floor to the bottom of the hole:
        self.height = cell_as_float(data, 'height')
        # how far from the start of the wall the hole starts:
        self.offset = cell_as_float(data, 'offset')

    def __str__(self):
        return "<hole %s in box %s>" % (self.name, self.adjacent)

    def scad_string(self, parent):
        """Return the SCAD code for this hole."""
        # 10=floor_thickness
        return """    hole([%g, %g, 10], [90, 0, %g], [%g, %g, -40], %s, "%s");\n""" % (
            parent.dimensions[0] if self.direction == 'right' else 0,
            parent.dimensions[1] if self.direction == 'back' else 0,
            90 if self.direction in ('left', 'right') else 0,
            self.offset, self.height,
            self.dimensions,
            self.name)

    def write_scad(self, stream, parent):
        """Write the SCAD code for this hole."""
        stream.write(self.scad_string(parent))

class Constant:

    """A constant definition."""

    pass

    def __init__(self, data):
        self.name = data['name']
        self.value = data['width']
        self.all_data = data

    def __str__(self):
        return "<defined constant %s=%s>" % (self.name, self.value)

class Type:

    """A type definition.

    Not implemented yet."""

    pass

    def __init__(self, data):
        self.data = data
        self.name = data['name']
        makers[self.name] = makers['__custom__']

class Custom:

    """A custom type, as defined by the Type type of row."""

    pass

    def __init__(self, data):
        self.data = data

# Define all the names for each of the functions to make an object
# from a spreadsheet row (since there are multiple names for each
# function, it is neater to write them this way, then invert the
# table):
names_for_makers = {
    lambda row, opacity: Box(row, opacity): ('room', 'shelf', 'shelves', 'box'),
    lambda row, _: Hole(row): ('door', 'window'),
    lambda row, _: Constant(row): ('constant',),
    lambda row, _: Type(row): ('type',),
    lambda row, _: Custom(row): ('__custom__',)}

# Invert the table, so we can look up row types in it:
makers = {
    name: maker
    for maker, names in names_for_makers.items()
    for name in names}

def position_dependents(boxes, dependents, box, level):
    """Position boxes dependent on a given box.
    Then position their dependents, etc."""
    if box.name in dependents:
        for dependent_name in dependents[box.name]:
            dependent = boxes[dependent_name]

            if isinstance(dependent, Box):

                # scan through the coordinates: X, Y, Z for
                # neighbouring boxes that begin where the current one
                # ends:

                for index, direction in enumerate(['right', 'behind', 'above']):
                    if dependent.direction == direction:
                        dependent.position[index] = (box.position[index]
                                                     + box.dimensions[index])

                for index, direction in enumerate(['left', 'front', 'below']):
                    if dependent.direction == direction:
                        dependent.position[index] = (box.position[index]
                                                     - dependent.dimensions[index])

                # scan through the coordinates: X, Y, Z for
                # neighbouring boxes that are coterminous with the
                # current one:

                for index, direction in enumerate(['left', 'front', 'bottom']):
                    if direction in dependent.alignment:
                        dependent.position[index] = (box.position[index]
                                                     + dependent.offset)

                for index, direction in enumerate(['right', 'back', 'top']):
                    if direction in dependent.alignment:
                        dependent.position[index] = (box.position[index]
                                                     + box.dimensions[index]
                                                     - dependent.dimensions[index]
                                                     + dependent.offset)

            elif isinstance(dependent, Hole):
                box.holes.append(dependent)

            position_dependents(boxes, dependents, dependent, level)

DEFAULT_CONSTANTS = {
    'wall_thickness': 10,
    'floor_thickness': 10,
    'ceiling_thickness': -1     # so we can see into rooms from above
}

def add_default_constants(boxes):
    """Set constants if not loaded from file."""
    for default_name, default_value in DEFAULT_CONSTANTS.items():
        if default_name not in boxes:
            boxes[default_name] = Constant({'name': default_name, 'width': default_value})

def read_layout(filename, opacity):
    """Read a file of layout data."""
    with open(filename) as instream:
        return {row['name']: makers[row.get('type', 'room')](row, opacity)
                for row in csv.DictReader(instream)}

def adjust_dimensions(boxes):
    """Add some dimensional details."""
    add_default_constants(boxes)

    wall_thickness = boxes['wall_thickness'].value
    floor_thickness = boxes['floor_thickness'].value
    ceiling_thickness = boxes['ceiling_thickness'].value

    # The dimensions of rooms are presumed to be given as internal:
    for box in boxes.values():
        if isinstance(box, Box) and box.box_type == 'room':
            box.dimensions[0] += wall_thickness # one half-thickness at each side
            box.dimensions[1] += wall_thickness # one half-thickness at each end
            box.dimensions[2] += floor_thickness + ceiling_thickness
        elif isinstance(box, Hole):
            box.dimensions[2] = wall_thickness * 8 # make sure it gets through
    return PREAMBLE0 % (wall_thickness, floor_thickness, ceiling_thickness)

def generate_tree(boxes):
    """Work out the tree structure of what depends on what."""
    dependents = {}
    first_box = None
    for box in boxes.values():
        if not isinstance(box, (Box, Hole)):
            continue
        adjacent = box.adjacent
        if adjacent == 'start':
            dependents['start'] = [box.name]
            first_box = box
        else:
            if adjacent not in dependents:
                dependents[adjacent] = []
            dependents[adjacent].append(box.name)
    return dependents, first_box

def show_tree(dependents, start='start', depth=0):
    """Show a tree of dependents."""
    if start in dependents:
        for child in dependents[start]:
            print("|   " * depth + child)
            show_tree(dependents, child, depth+1)

def make_scad_layout(input_file_name:str, output:str, opacity:float = 1.0, verbose:bool=False, debug:bool=False):
    """Read a layout definition file and produce a 3D model file from it."""
    boxes = read_layout(input_file_name, opacity)

    dependents, first_box = generate_tree(boxes)

    if verbose:
        show_tree(dependents)

    if 'start' not in dependents:
        print("No starting point given")

    sized_preamble = adjust_dimensions(boxes)

    # Now process the tree
    first_box.position = [0.0, 0.0, 0.0]
    position_dependents(boxes, dependents, first_box, 1)

    with open(output, 'w') as outstream:
        outstream.write("""// Produced from %s\n""" % input_file_name)
        outstream.write(sized_preamble)
        outstream.write(PREAMBLE1DEBUG if debug else PREAMBLE1)
        holes = "".join(box.write_scad(outstream)
                        for box in boxes.values()
                        if isinstance(box, Box))
        outstream.write(INTERAMBLEDEBUG if debug else INTERAMBLE)
        outstream.write(holes)
        outstream.write(POSTAMBLEDEBUG if debug else POSTAMBLE)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file_name")
    parser.add_argument("--output", "-o")
    parser.add_argument("--opacity", "--alpha", "-a", type=float, default=1.0)
    parser.add_argument("--verbose", "-v", action='store_true')
    parser.add_argument("--debug", "-d", action='store_true')
    args = parser.parse_args()

    make_scad_layout(args.input_file_name, args.output, args.opacity, args.verbose, args.debug)

if __name__ == '__main__':
    main()
