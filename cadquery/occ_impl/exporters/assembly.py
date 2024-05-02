import os.path
import uuid
from math import degrees

from tempfile import TemporaryDirectory
from shutil import make_archive
from itertools import chain
from typing import Optional
from typing_extensions import Literal

from vtkmodules.vtkIOExport import vtkJSONSceneExporter, vtkVRMLExporter
from vtkmodules.vtkRenderingCore import (
    vtkRenderer,
    vtkRenderWindow,
    vtkGraphicsFactory,
    vtkWindowToImageFilter,
    vtkActor,
    vtkPolyDataMapper as vtkMapper,
)
from vtkmodules.vtkFiltersExtraction import vtkExtractCellsByType
from vtkmodules.vtkCommonDataModel import VTK_TRIANGLE, VTK_LINE, VTK_VERTEX
from vtkmodules.vtkIOImage import vtkPNGWriter

from OCP.XSControl import XSControl_WorkSession
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.XCAFApp import XCAFApp_Application
from OCP.XmlDrivers import (
    XmlDrivers_DocumentStorageDriver,
    XmlDrivers_DocumentRetrievalDriver,
)
from OCP.TCollection import TCollection_ExtendedString, TCollection_AsciiString
from OCP.PCDM import PCDM_StoreStatus
from OCP.RWGltf import RWGltf_CafWriter
from OCP.TColStd import TColStd_IndexedDataMapOfStringString
from OCP.Message import Message_ProgressRange
from OCP.Interface import Interface_Static

from ..assembly import AssemblyProtocol, toCAF, toVTK, toFusedCAF
from ..geom import Location


class ExportModes:
    DEFAULT = "default"
    FUSED = "fused"


STEPExportModeLiterals = Literal["default", "fused"]


def exportAssembly(
    assy: AssemblyProtocol,
    path: str,
    mode: STEPExportModeLiterals = "default",
    **kwargs
) -> bool:
    """
    Export an assembly to a STEP file.

    kwargs is used to provide optional keyword arguments to configure the exporter.

    :param assy: assembly
    :param path: Path and filename for writing
    :param mode: STEP export mode. The options are "default", and "fused" (a single fused compound).
        It is possible that fused mode may exhibit low performance.
    :param fuzzy_tol: OCCT fuse operation tolerance setting used only for fused assembly export.
    :type fuzzy_tol: float
    :param glue: Enable gluing mode for improved performance during fused assembly export.
        This option should only be used for non-intersecting shapes or those that are only touching or partially overlapping.
        Note that when glue is enabled, the resulting fused shape may be invalid if shapes are intersecting in an incompatible way.
        Defaults to False.
    :type glue: bool
    :param write_pcurves: Enable or disable writing parametric curves to the STEP file. Default True.
        If False, writes STEP file without pcurves. This decreases the size of the resulting STEP file.
    :type write_pcurves: bool
    :param precision_mode: Controls the uncertainty value for STEP entities. Specify -1, 0, or 1. Default 0.
        See OCCT documentation.
    :type precision_mode: int
    """

    # Handle the extra settings for the STEP export
    pcurves = 1
    if "write_pcurves" in kwargs and not kwargs["write_pcurves"]:
        pcurves = 0
    precision_mode = kwargs["precision_mode"] if "precision_mode" in kwargs else 0
    fuzzy_tol = kwargs["fuzzy_tol"] if "fuzzy_tol" in kwargs else None
    glue = kwargs["glue"] if "glue" in kwargs else False

    # Use the assembly name if the user set it
    assembly_name = assy.name if assy.name else str(uuid.uuid1())

    # Handle the doc differently based on which mode we are using
    if mode == "fused":
        _, doc = toFusedCAF(assy, glue, fuzzy_tol)
    else:  # Includes "default"
        _, doc = toCAF(assy, True)

    session = XSControl_WorkSession()
    writer = STEPCAFControl_Writer(session, False)
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)
    Interface_Static.SetIVal_s("write.surfacecurve.mode", pcurves)
    Interface_Static.SetIVal_s("write.precision.mode", precision_mode)
    writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)

    status = writer.Write(path)

    return status == IFSelect_ReturnStatus.IFSelect_RetDone


def exportCAF(assy: AssemblyProtocol, path: str) -> bool:
    """
    Export an assembly to a OCAF xml file (internal OCCT format).
    """

    folder, fname = os.path.split(path)
    name, ext = os.path.splitext(fname)
    ext = ext[1:] if ext[0] == "." else ext

    _, doc = toCAF(assy)
    app = XCAFApp_Application.GetApplication_s()

    store = XmlDrivers_DocumentStorageDriver(
        TCollection_ExtendedString("Copyright: Open Cascade, 2001-2002")
    )
    ret = XmlDrivers_DocumentRetrievalDriver()

    app.DefineFormat(
        TCollection_AsciiString("XmlOcaf"),
        TCollection_AsciiString("Xml XCAF Document"),
        TCollection_AsciiString(ext),
        ret,
        store,
    )

    doc.SetRequestedFolder(TCollection_ExtendedString(folder))
    doc.SetRequestedName(TCollection_ExtendedString(name))

    status = app.SaveAs(doc, TCollection_ExtendedString(path))

    app.Close(doc)

    return status == PCDM_StoreStatus.PCDM_SS_OK


def _vtkRenderWindow(
    assy: AssemblyProtocol, tolerance: float = 1e-3, angularTolerance: float = 0.1
) -> vtkRenderWindow:
    """
    Convert an assembly to a vtkRenderWindow. Used by vtk based exporters.
    """

    renderer = toVTK(assy, tolerance=tolerance, angularTolerance=angularTolerance)
    renderWindow = vtkRenderWindow()
    renderWindow.AddRenderer(renderer)

    renderer.ResetCamera()
    renderer.SetBackground(1, 1, 1)

    return renderWindow


def exportVTKJS(assy: AssemblyProtocol, path: str):
    """
    Export an assembly to a zipped vtkjs. NB: .zip extensions is added to path.
    """

    renderWindow = _vtkRenderWindow(assy)

    with TemporaryDirectory() as tmpdir:

        exporter = vtkJSONSceneExporter()
        exporter.SetFileName(tmpdir)
        exporter.SetRenderWindow(renderWindow)
        exporter.Write()
        make_archive(path, "zip", tmpdir)


def exportVRML(
    assy: AssemblyProtocol,
    path: str,
    tolerance: float = 1e-3,
    angularTolerance: float = 0.1,
):
    """
    Export an assembly to a vrml file using vtk.
    """

    exporter = vtkVRMLExporter()
    exporter.SetFileName(path)
    exporter.SetRenderWindow(_vtkRenderWindow(assy, tolerance, angularTolerance))
    exporter.Write()


def exportGLTF(
    assy: AssemblyProtocol,
    path: str,
    binary: Optional[bool] = None,
    tolerance: float = 1e-3,
    angularTolerance: float = 0.1,
):
    """
    Export an assembly to a gltf file.
    """

    # If the caller specified the binary option, respect it
    if binary is None:
        # Handle the binary option for GLTF export based on file extension
        binary = True
        path_parts = path.split(".")

        # Binary will be the default if the user specified a non-standard file extension
        if len(path_parts) > 0 and path_parts[-1] == "gltf":
            binary = False

    # map from CadQuery's right-handed +Z up coordinate system to glTF's right-handed +Y up coordinate system
    # https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#coordinate-system-and-units
    orig_loc = assy.loc
    assy.loc *= Location((0, 0, 0), (1, 0, 0), -90)

    _, doc = toCAF(assy, True, True, tolerance, angularTolerance)

    writer = RWGltf_CafWriter(TCollection_AsciiString(path), binary)
    result = writer.Perform(
        doc, TColStd_IndexedDataMapOfStringString(), Message_ProgressRange()
    )

    # restore coordinate system after exporting
    assy.loc = orig_loc

    return result


def exportPNG(
    assy: AssemblyProtocol, path: str, opts: Optional[dict] = None,
):
    """
    Exports an assembly to a VTK object, which can then be rendered to a PNG image
    while preserving colors, rotation, etc.
    :param assy: Assembly to be exported to PNG
    :param path: Path and filename for writing the PNG data to
    :param opts: Options that influence the way the PNG is rendered
    """

    face_actors = []
    edge_actors = []

    # Walk the assembly tree to make sure all objects are exported
    for subassy in assy.traverse():
        for shape, name, loc, col in subassy[1]:
            color = col.toTuple() if col else (0.1, 0.1, 0.1, 1.0)
            translation, rotation = loc.toTuple()

            # Tesselate the CQ object into VTK data
            vtk_data = shape.toVtkPolyData(1e-3, 0.1)

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
            edge_actor.GetProperty().SetColor(1.0, 1.0, 1.0)
            edge_actor.GetProperty().SetLineWidth(1)

            # Handle all actors
            face_actors.append(face_actor)
            edge_actors.append(edge_actor)

    # We need a compound assembly object so we can get the size for the camera position
    assy_compound = assy.toCompound()

    # Try to determine sane defaults for the camera position
    camera_x = 20
    camera_y = 20
    camera_z = 20
    if not opts or "camera_position" not in opts:
        camera_x = (
            assy_compound.BoundingBox().xmax - assy_compound.BoundingBox().xmin
        ) * 2.0
        camera_y = (
            assy_compound.BoundingBox().ymax - assy_compound.BoundingBox().ymin
        ) * 2.0
        camera_z = (
            assy_compound.BoundingBox().zmax - assy_compound.BoundingBox().zmin
        ) * 2.0

    # Handle view options that were passed in
    if opts:
        width = opts["width"] if "width" in opts else 800
        height = opts["height"] if "height" in opts else 600
        camera_position = (
            opts["camera_position"]
            if "camera_position" in opts
            else (camera_x, camera_y, camera_z)
        )
        view_up_direction = (
            opts["view_up_direction"] if "view_up_direction" in opts else (0, 0, 1)
        )
        focal_point = opts["focal_point"] if "focal_point" in opts else (0, 0, 0)
        parallel_projection = (
            opts["parallel_projection"] if "parallel_projection" in opts else True
        )
        background_color = (
            opts["background_color"] if "background_color" in opts else (0.5, 0.5, 0.5)
        )
        clipping_range = opts["clipping_range"] if "clipping_range" in opts else None
    else:
        width = 800
        height = 600
        camera_position = (camera_x, camera_y, camera_z)
        view_up_direction = (0, 0, 1)
        focal_point = (0, 0, 0)
        parallel_projection = False
        background_color = (0.8, 0.8, 0.8)
        clipping_range = None

    # Setup offscreen rendering
    graphics_factory = vtkGraphicsFactory()
    graphics_factory.SetOffScreenOnlyMode(1)
    graphics_factory.SetUseMesaClasses(1)

    # A renderer and render window
    renderer = vtkRenderer()
    renderWindow = vtkRenderWindow()
    renderWindow.SetSize(width, height)
    renderWindow.SetOffScreenRendering(1)

    renderWindow.AddRenderer(renderer)

    # Add all the actors to the scene
    for face_actor in face_actors:
        renderer.AddActor(face_actor)
    for edge_actor in edge_actors:
        renderer.AddActor(edge_actor)

    renderer.SetBackground(
        background_color[0], background_color[1], background_color[2]
    )

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

    # Set the clipping range
    if clipping_range:
        camera.SetClippingRange(clipping_range[0], clipping_range[1])

    # Export a PNG of the scene
    windowToImageFilter = vtkWindowToImageFilter()
    windowToImageFilter.SetInput(renderWindow)
    windowToImageFilter.Update()

    writer = vtkPNGWriter()
    writer.SetFileName(path)
    writer.SetInputConnection(windowToImageFilter.GetOutputPort())
    writer.Write()
