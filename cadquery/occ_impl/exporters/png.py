from math import degrees
from vtkmodules.vtkRenderingCore import vtkGraphicsFactory
from vtkmodules.vtkCommonColor import vtkNamedColors
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper as vtkMapper,
    vtkRenderer
)
from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkRenderWindowInteractor, vtkWindowToImageFilter
from vtkmodules.vtkFiltersExtraction import vtkExtractCellsByType
from vtkmodules.vtkCommonDataModel import VTK_TRIANGLE, VTK_LINE, VTK_VERTEX
from vtkmodules.vtkIOImage import vtkPNGWriter
import cadquery as cq


def process_cq_object(cq_obj):
    """
    Converts a CadQuery shape into VTK face and edge actors for rendering.
    """

    # Tesselate the CQ object into VTK data
    vtk_data = cq_obj.toVtkPolyData(1e-3, 0.1, True)
    color = (0.04, 0.5, 0.67, 1.0)
    translation = (0, 0, 0)
    rotation = (0, 0, 0)

    # Extract faces
    extr = vtkExtractCellsByType()
    extr.SetInputDataObject(vtk_data)

    extr.AddCellType(VTK_LINE)
    extr.AddCellType(VTK_VERTEX)
    extr.Update()
    data_edges = extr.GetOutput()

    # Extract edges
    extr = vtkExtractCellsByType()
    extr.SetInputDataObject(vtk_data)

    extr.AddCellType(VTK_TRIANGLE)
    extr.Update()
    data_faces = extr.GetOutput()

    # Remove normals from edges
    data_edges.GetPointData().RemoveArray("Normals")

    # Set up the face and edge mappers and actors
    face_mapper = vtkMapper()
    face_actor = vtkActor()
    face_actor.SetMapper(face_mapper)
    edge_mapper = vtkMapper()
    edge_actor = vtkActor()
    edge_actor.SetMapper(edge_mapper)

    # Update the faces
    face_mapper.SetInputDataObject(data_faces)
    face_actor.SetPosition(*translation)
    face_actor.SetOrientation(*map(degrees, rotation))
    face_actor.GetProperty().SetColor(*color[:3])
    face_actor.GetProperty().SetOpacity(color[3])

    # Update the edges
    edge_mapper.SetInputDataObject(data_edges)
    edge_actor.SetPosition(*translation)
    edge_actor.SetOrientation(*map(degrees, rotation))
    edge_actor.GetProperty().SetColor(0.8, 0.8, 0.8)
    edge_actor.GetProperty().SetLineWidth(1)

    return (face_actor, edge_actor)


def exportPNG(shape, fileName: str, opts=None):
    """
    Accepts a CadQuery shape, and exports it in PNG bitmap format at the provided path.

    :param shape: Shape object to be exported to PNG
    :param fileName: The output path and filename
    :param opts: Options that influence the way the PNG is rendered
    """

    # Try to determine sane defaults for the camera position
    camera_x = 20
    camera_y = 20
    camera_z = 20
    if "camera_position" not in opts:
        camera_x = (shape.BoundingBox().xmax - shape.BoundingBox().xmin) * 2.0
        camera_y = (shape.BoundingBox().ymax - shape.BoundingBox().ymin) * 2.0
        camera_z = (shape.BoundingBox().zmax - shape.BoundingBox().zmin) * 2.0


    # Handle view options that were passed in
    if opts:
        width = opts["width"] if "width" in opts else 800
        height = opts["height"] if "height" in opts else 600
        camera_position = opts["camera_position"] if "camera_position" in opts else (camera_x, camera_y, camera_z)
        view_up_direction = opts["view_up_direction"] if "view_up_direction" in opts else (0, 0, 1)
        focal_point = opts["focal_point"] if "focal_point" in opts else (0, 0, 0)
        parallel_projection = opts["parallel_projection"] if "parallel_projection" in opts else False
        background_color = opts["background_color"] if "background_color" in opts else (0.5, 0.5, 0.5)
    else:
        width = 800
        height = 600
        camera_position = (camera_x, camera_y, camera_z)
        view_up_direction = (0, 0, 1)
        focal_point = (0, 0, 0)
        parallel_projection = False
        background_color = (0.5, 0.5, 0.5)

    colors = vtkNamedColors()

    # Setup offscreen rendering
    graphics_factory = vtkGraphicsFactory()
    graphics_factory.SetOffScreenOnlyMode(1)
    graphics_factory.SetUseMesaClasses(1)

    # Process the CadQuery object into faces and edges
    face_actor, edge_actor = process_cq_object(shape)

    # A renderer and render window
    renderer = vtkRenderer()
    renderWindow = vtkRenderWindow()
    renderWindow.SetSize(width, height)
    renderWindow.SetOffScreenRendering(1)

    renderWindow.AddRenderer(renderer)

    # Add the actors to the scene
    renderer.AddActor(face_actor)
    renderer.AddActor(edge_actor)

    renderer.SetBackground(background_color[0], background_color[1], background_color[2])

    # Render the scene
    renderWindow.Render()

    # Set the camera as the user requested
    camera = renderer.GetActiveCamera()
    camera.SetPosition(camera_position[0], camera_position[1], camera_position[2])
    camera.SetViewUp(view_up_direction[0], view_up_direction[1], view_up_direction[2])
    camera.SetFocalPoint(focal_point[0], focal_point[1], focal_point[2])
    if parallel_projection:
        camera.ParallelProjectionOn()
    else:
        camera.ParallelProjectionOff()

    # Export a PNG of the scene
    windowToImageFilter = vtkWindowToImageFilter()
    windowToImageFilter.SetInput(renderWindow)
    windowToImageFilter.Update()

    writer = vtkPNGWriter()
    writer.SetFileName(fileName)
    writer.SetInputConnection(windowToImageFilter.GetOutputPort())
    writer.Write()
