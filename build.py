#!/usr/bin/env python3

# TODO:
#  - landing page with template controls
#  - use manifest to define updatable fields
#  - fix favicon
#  - fix keyboard interrupt warings (cherrypy)
#

import os
import sys
import time
import copy
import json
import zipfile
import shutil

import sass
import jsmin
import htmlmin
import jinja2

try:
    import pyinotify
    has_inotify = True
except ImportError:
    has_inotify = False

from nxtools import *

logging.show_time = True

#
# Application settings
#

settings = {
    "src_dir" : "src",
    "build_dir" : "build",
    "dist_dir" : "dist",
}

for key in settings:
    if key.endswith("_dir"):
        # All directories in settings ends with '_dir'
        # We want to use absolute paths so we convert
        # all relative paths and expand ~ to the user's home directory
        settings[key] = os.path.abspath(os.path.expanduser(settings[key])).rstrip("/")

#
# Minifiers
#

def process_js(source_path: str) -> str:
    """Opens a javascript file specified by path,
    returns minified version of the script as a string.

    Returns empty string if the path does not exist.

    Args:
        source_path (str): Path to the source js file

    Returns:
        str: Minified version of the script
    """
    try:
        with open(source_path) as js_file:
           # return js_file.read()
            minified = jsmin.jsmin(js_file.read())
            return minified
    except:
        return ""


def process_sass(source_path: str) -> str:
    """Opens a SASS file specified by path,
    returns minified CSS as a string.

    Returns empty string if the path does not exist.

    Args:
        source_path (str): Path to the source sass file

    Returns:
        str: Resulting minified CSS
    """
    with open(source_path) as sass_file:
        minified = sass.compile(
                string=sass_file.read(),
                indented=os.path.splitext(source_path)[1] == ".sass",
                output_style="compressed"
            )
        return minified

#
# Template builder
#

class TemplateBuilder():
    def __init__(self):
        self.ctx = {
            "core_css" : process_sass("core/core.sass"),
            "core_js" : process_js("core/core.js")
        }
        with open("core/core.html") as f:
            self.template = jinja2.Template(f.read())

    @property
    def templates(self) -> list:
        """Returns a list of templates available in the source directory
        """
        return [d for d in os.listdir(settings["src_dir"]) \
            if os.path.isdir(os.path.join(settings["src_dir"], d)) ]

    def _build(self, name: str) -> bool:
        source_dir    = os.path.join("src", name)
        tpl_html_path = os.path.join(source_dir, "template.html")
        tpl_sass_path = os.path.join(source_dir, "template.sass")
        tpl_js_path   = os.path.join(source_dir, "template.js")
        manifest_path = os.path.join(source_dir, "manifest.json")
        logging.info("Building template", name)

        ctx = copy.deepcopy(self.ctx)

        if os.path.exists(tpl_sass_path) and os.path.getsize(tpl_sass_path):
            ctx["tpl_css"] = process_sass(tpl_sass_path)

        if os.path.exists(tpl_js_path):
            ctx["tpl_js"] = process_js(tpl_js_path)

        if os.path.exists(tpl_html_path):
            ctx["body"] = open(tpl_html_path).read()

        manifest = {}
        if os.path.exists(manifest_path):
            manifest = json.load(open(manifest_path))
        ctx["manifest"] = manifest

        param_map = "var param_map = {\n"
        for i, param in enumerate(manifest.get("parameters", [])):
            param_map += f"   'f{i}' : '{param['id']}',\n"
        param_map+= "}"

        ctx["param_map"] = param_map

        result = self.template.render(**ctx)
        result = htmlmin.minify(
                result,
                remove_comments=True,
                remove_empty_space=True,
                remove_optional_attribute_quotes=False
            )

        tpl_header_data = {
            "version" : "2.0.0",
            "author_name" : manifest.get("author_name", "Nebula Broadcast"),
            "author_email" : manifest.get("author_email", "info@nebulabroadcast.com"),
            "template_info" : "",
            "width" : manifest.get("width", 1920),
            "height" : manifest.get("height", 1080),
            "frame_rate" : manifest.get("frame_rate", 50),
        }

        tplinfo = "<template"
        tplinfo += " version=\"{version}\""
        tplinfo += " authorName=\"{author_name}\""
        tplinfo += " authorEmail=\"{author_email}\""
        tplinfo += " templateInfo=\"{template_info}\""
        tplinfo += " originalWidth=\"{width}\""
        tplinfo += " originalHeight=\"{height}\""
        tplinfo += " originalFrameRate=\"{frame_rate}\">\n"

        tplinfo = tplinfo.format(**tpl_header_data)

        tplinfo += "  <components/>\n"
        tplinfo += "  <keyframes/>\n"
        tplinfo += "  <instances/>\n"

        tplinfo += "  <parameters>\n"
        for param in manifest.get("parameters", []):
            tplinfo += "    <parameter id=\"{}\" type=\"{}\" info=\"{}\"/>\n".format(
                        param["id"],
                        param.get("type", "string"),
                        param.get("info", "")

                    )
        tplinfo += "  </parameters>\n"
        tplinfo += "</template>\n"


        # Create destination directory "build/template_name"
        target_dir = os.path.join(settings["build_dir"], name)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        with open(os.path.join(target_dir, name + ".html"), "w") as f:
            f.write(result)

        with open(os.path.join(target_dir, name + ".xml"), "w") as f:
            f.write(tplinfo)

        for depname in os.listdir(source_dir):
            if depname in ["template.html", "template.sass", "template.scss", "template.js", "manifest.json"]:
                continue
            dep_src = os.path.join(source_dir, depname)
            dep_tgt = os.path.join(target_dir, depname)
            shutil.copy(dep_src, dep_tgt)


        return True

    def build(self, name: str) -> bool:
        start_time = time.time()
        try:
            self._build(name)
        except Exception:
            log_traceback(f"Building of {name} failed".format(name))
            return False
        logging.goodnews(f"Building of {name} finished in {time.time() - start_time:.03f}s")
        return True

builder = TemplateBuilder()

#
# Watch / autobuild
#

if has_inotify:
    class SrcChangeHandler(pyinotify.ProcessEvent):
        def my_init(self, msg):
            self._msg = msg

        def process_default(self, event):
            pathname = event.pathname.replace(settings["src_dir"], "", 1)
            pathname = pathname.lstrip("/")
            template_name = pathname.split("/")[0]
            if not template_name in builder.templates:
                return
            builder.build(template_name)

    def watch():
        """Watch the source directory for changes.
        This function is blocking, so it's called last.
        """
        logging.info("Watching", settings["src_dir"])
        wm = pyinotify.WatchManager()
        handler = SrcChangeHandler(msg="changed")
        notifier = pyinotify.Notifier(wm, default_proc_fun=handler)
        wm.add_watch(
                settings["src_dir"],
                pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_CREATE,
                rec=True,
                auto_add=True
            )
        notifier.loop()
else:
    watch = None


if __name__ == '__main__':
    # Build all templates on start-up
    for template in builder.templates:
        builder.build(template)

    if "--dist" in sys.argv:
        if not os.path.exists(settings["dist_dir"]):
            os.makedirs(settings["dist_dir"])
        for template in builder.templates:
            tdir = os.path.join(settings["build_dir"], template)
            zipname = os.path.join(settings["dist_dir"], template + ".zip")
            with zipfile.ZipFile(zipname, "w") as z:
                for folderName, subfolders, filenames in os.walk(tdir):
                    for filename in filenames:
                        filePath = os.path.join(folderName, filename)
                        z.write(filePath, os.path.basename(filePath))


        sys.exit(0)

    if watch and "--watch" in sys.argv:
        # Watch the source directory for changes
        try:
            watch()
        except KeyboardInterrupt:
            print()
            logging.info("Keyboard interrupt. Shutting down")
            sys.exit(0)
