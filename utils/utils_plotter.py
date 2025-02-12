import subprocess
import os


def export_figure(figure, **kwargs):
    """
    Saves figure as .emf
    :param figure: fig handle
    :param kwargs: filepath: str                File name, e.g. '*\filename'
    :return: None
    """
    inkscape_path = kwargs.get('inkscape', "C://Program Files//Inkscape//bin//inkscape.exe")
    filepath = kwargs.get('filename', None)
    filetype = kwargs.get('filetype', None)
    if filepath is not None:
        path, filename = os.path.split(filepath)
        filename, extension = os.path.splitext(filename)
        svg_filepath = os.path.join(path, filename + '.svg')
        target_filepath = os.path.join(path, filename + f'.{filetype}')
        figure.savefig(svg_filepath, bbox_inches='tight', format='svg')
        subprocess.call([inkscape_path, svg_filepath, f'--export-{filetype}', target_filepath])
        # os.remove(svg_filepath)
