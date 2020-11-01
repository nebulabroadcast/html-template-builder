#!/usr/bin/env python3

#
# TODO:
#  - Web server
#  - landing page with template controls
#  - use manifest to define updatable fields
#

from logging import shutdown
import os
import time
import copy
import json

import sass
import jsmin
import htmlmin
import jinja2

import _thread

import cherrypy
import pyinotify

from nxtools import *

#
# Application settings
#

settings = {
    "src_dir" : "src",
    "dist_dir" : "dist",
    "web_host" : "0.0.0.0",
    "web_port" : 8090
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
    """Opens an javascript file specified by path, 
    returns minified version of the script as a string.

    Returns empty string if path does not exist.

    Args:
        source_path (str): Path to the source js file
    
    Returns:
        str: Minified version of the script
    """
    try:
        with open(source_path) as js_file:
            minified = jsmin.jsmin(js_file.read())
            return minified
    except:
        return ""


def process_sass(source_path: str) -> str:
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
    def templates(self):
        return [d for d in os.listdir(settings["src_dir"]) \
            if os.path.isdir(os.path.join(settings["src_dir"], d)) ]

    def _build(self, name: str) -> bool:
        source_dir = os.path.join("src", name)
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

        result = self.template.render(**ctx)
        result = htmlmin.minify(
                result,
                remove_comments=True,
                remove_empty_space=True,
                remove_optional_attribute_quotes=False
            )
        with open(os.path.join("dist", name + ".html"), "w") as f:
            f.write(result)
        return True
    
    def build(self, name: str) -> bool:
        start_time = time.time()
        try:
            self._build(name)
        except Exception:
            log_traceback("Building of {} failed".format(name))
            return False
        logging.goodnews("Building of {} finished in {:.03f}s".format(name, time.time() - start_time))

builder = TemplateBuilder()


#
# Web server
#

class WebServerHander():
    def __init__(self, server):
        self.server = server

    @cherrypy.expose
    def index(self, *args, **kwargs):
        return "index"

    def cherrypy_error(self, *args, **kwargs):
        return "Error {} {}".format(args, kwargs)


class WebServer():
    def __init__(self):
        self.is_running = False
        self.handler = WebServerHander(self)
        static_root, static_dir = os.path.split(settings["dist_dir"]) 
        self.config = {
            '/': {
                'tools.proxy.on': True,
                'tools.proxy.local': 'X-Forwarded-Host',
                'tools.proxy.local': 'Host',
                'tools.staticdir.root': static_root,
                'tools.trailing_slash.on' : False,
                'error_page.default': self.handler.cherrypy_error,
                },

            '/template': {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': static_dir
                },

            '/favicon.ico': {
                'tools.staticfile.on': True,
                'tools.staticfile.filename': os.path.join(static_root, static_dir, "img", "favicon.ico")
                },
            }

        cherrypy.config.update({
            "server.socket_host" : settings["web_host"],
            "server.socket_port" : settings["web_port"],
            'engine.autoreload.on' : False,
            "log.screen" : False
        })


    def start(self): 
        logging.info("Starting web server")
        cherrypy.tree.mount(self.handler, "/", self.config)
        cherrypy.engine.subscribe('start', self.on_start)
        cherrypy.engine.subscribe('stop', self.on_stop)
        cherrypy.engine.start()
        cherrypy.engine.block()

    def on_start(self):
        logging.goodnews("Web server started")
        self.is_running = True

    def on_stop(self):
        logging.warning("Web service stopped")
        self.is_running = False

    def shutdown(self):
        cherrypy.engine.exit()


#
# Watch / autobuild
#

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


if __name__ == '__main__':
    # Build all templates on start-up
    for template in builder.templates:
        builder.build(template)

    # Enable web server
    server = WebServer()
    _thread.start_new_thread(server.start, ())
    

    # Watch source directory for changes
    try:
        watch()
    except KeyboardInterrupt:
        print()
        logging.info("Keyboard interrupt. Shutting down")
        server.shutdown()
        sys.exit(0)
