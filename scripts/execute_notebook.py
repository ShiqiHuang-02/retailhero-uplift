"""Execute one trusted project notebook in an isolated process, without sockets."""
import contextlib
import io
import os
from pathlib import Path
import sys
import traceback

import nbformat
from IPython.core.interactiveshell import InteractiveShell


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    path = (root / sys.argv[1]).resolve()
    if path.parent != root or path.suffix != '.ipynb':
        raise ValueError('Only project-root notebooks may be executed')
    notebook = nbformat.read(path, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    shell = InteractiveShell.instance()
    # The inline backend embeds figures in the saved notebook and needs no GUI.
    import matplotlib
    matplotlib.use('module://matplotlib_inline.backend_inline')
    from matplotlib_inline.backend_inline import configure_inline_support
    configure_inline_support(shell, 'inline')
    try:
        count = 0
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type != 'code':
                continue
            count += 1
            cell.execution_count = count
            print(f'{path.name}: cell {index}', flush=True)
            stdout, stderr = io.StringIO(), io.StringIO()
            def flush_streams():
                for name, stream in [('stdout', stdout), ('stderr', stderr)]:
                    text = stream.getvalue()
                    if text:
                        cell.outputs.append(nbformat.v4.new_output('stream', name=name, text=text))
                        stream.seek(0)
                        stream.truncate(0)
            def publish(data, metadata=None, **kwargs):
                flush_streams()
                cell.outputs.append(nbformat.v4.new_output('display_data', data=data, metadata=metadata or {}))
            def execute_result(format_dict, md_dict=None):
                flush_streams()
                cell.outputs.append(nbformat.v4.new_output('execute_result', data=format_dict,
                    metadata=md_dict or {}, execution_count=count))
            shell.display_pub.publish = publish
            shell.displayhook.write_format_data = execute_result
            shell.displayhook.write_output_prompt = lambda: None
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = shell.run_cell(cell.source, store_history=True)
            flush_streams()
            error = result.error_before_exec or result.error_in_exec
            if error is not None:
                cell.outputs.append(nbformat.v4.new_output('error', ename=type(error).__name__,
                    evalue=str(error), traceback=traceback.format_exception(error)))
                raise error
    finally:
        nbformat.write(notebook, path)


if __name__ == '__main__':
    main()
