from cadquery.assembly import Assembly


def exportPNG(shape, path: str, opts=None):
    """
    Accepts a CadQuery shape, and exports it in PNG bitmap format at the provided path.
    It does this by first converting the shape to an assembly so that it can be run though
    that exporter to avoid duplication of code and functionality.

    :param shape: Shape object to be exported to PNG
    :param path: The output path and filename
    :param opts: Options that influence the way the PNG is rendered
    """

    assy = Assembly(shape)
    assy.save(path, opt=opts)
