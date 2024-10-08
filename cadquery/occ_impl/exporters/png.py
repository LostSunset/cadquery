def exportPNG(model, path: str, opts=None):
    """
    Accepts a CadQuery shape, and exports it in PNG bitmap format at the provided path.
    It does this by first converting the shape to an assembly so that it can be run though
    that exporter to avoid duplication of code and functionality.

    :param model: Shape or Assembly object to be exported to PNG
    :param path: The output path and filename
    :param opts: Options that influence the way the PNG is rendered
    """
    print("exportPNG")
    print(opts)
    # Check to see if the shape is an instance of the Assembly class
    if type(model).__name__ == "Assembly":
        model.export(path, opts=opts)
    # else:
    #     export(shape, path, opts=opts)
