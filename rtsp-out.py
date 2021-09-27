from os import link, pipe
import os
import numpy as np
import math
import sys
import numpy as np
from numpy.core.records import array
sys.path.append('../')
import configparser
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GObject, Gst
from gi.repository import GLib
from gi.repository import GObject, Gst, GstRtspServer
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call


MAX_DISPLAY_LEN=64
MUXER_OUTPUT_WIDTH=1920
MUXER_OUTPUT_HEIGHT=1080
MUXER_BATCH_TIMEOUT_USEC=4000000
TILED_OUTPUT_WIDTH=1280
TILED_OUTPUT_HEIGHT=720
GST_CAPS_FEATURES_NVMM="memory:NVMM"


def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad")
    caps=decoder_src_pad.get_current_caps()
    gststruct=caps.get_structure(0)
    gstname=gststruct.get_name()
    source_bin=data
    features=caps.get_features(0)

    if(gstname.find("video")!=-1):
    
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad=source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("ERROR: Failed to link decoder src pad to source bin ghost pad\n")
                sys.exit(1)
        else:
            sys.stderr.write("ERROR: Decodebin did not pick nvidia decoder plugin.\n")
            sys.exit(1)

def decodebin_child_added(child_proxy,Object,name,user_data):
    print("Decodebin child added:" + name)
    if(name.find("decodebin") != -1):
        Object.connect("child-added",decodebin_child_added,user_data)
    if(is_aarch64() and name.find("nvv4l2decoder") != -1):
        print("Seting bufapi_version")
        Object.set_property("bufapi-version",True)

def create_source_bin(index,uri):
    print("Creating source bin\n")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name="source-bin-%02d" %index
    print(bin_name)
    nbin=Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write("ERROR: Unable to create source bin")
        sys.exit(1)

    uri_decode_bin=Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write("ERROR: Unable to create uri decode bin")
        sys.exit(1)
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri",uri)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added",cb_newpad,nbin)
    uri_decode_bin.connect("child-added",decodebin_child_added,nbin)

    Gst.Bin.add(nbin,uri_decode_bin)
    bin_pad=nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write("ERROR: Failed to add ghost pad in source bin")
        sys.exit(1)
    return nbin


def main(args):
    if len(args) < 2:
        sys.stderr.write("usage: %s <uri1> [uri2] ... [uriN]\n" % args[0])
        sys.exit(1)

    number_sources=len(args)-1

    # Standard GStreamer initialization
    GObject.threads_init()
    Gst.init(None)

    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    is_live = False

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")
    print("Creating streamux \n ")

    # Create nvstreammux instance to form batches from one or more sources.
    print("Creating elements to recevice RTSP streams as the video input - Streammux\n")
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")
   
    print("Creating elements to separate out Streamdemux\n")
    streamdemux = Gst.ElementFactory.make("nvstreamdemux", "Stream-demuxer")

    if not streamdemux:
        sys.stderr.write(" Unable to create NvStreamdeMux \n")
    pipeline.add(streammux)
    for i in range(number_sources):
        print("Creating source_bin ",i," \n ")
        uri_name=args[i+1]
        if uri_name.find("rtsp://") == 0 :
            is_live = True
        source_bin=create_source_bin(i, uri_name)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
        pipeline.add(source_bin)
        padname="sink_%u" %i
        sinkpad= streammux.get_request_pad(padname) 
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
        srcpad=source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
        srcpad.link(sinkpad)


    print("Creating tiler \n ")
    tiler1=Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler1")
    tiler2=Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler2")
    if not tiler1:
        sys.stderr.write(" Unable to create tiler \n")
    tiler=[tiler1, tiler2]

    print("Creating nvvidconv \n ")
    nvvidconv1 = Gst.ElementFactory.make("nvvideoconvert", "convertor1")
    nvvidconv2 = Gst.ElementFactory.make("nvvideoconvert", "convertor2")
    if not nvvidconv1:
        sys.stderr.write("Unable to create nvvidconv\n")
    nvvidconv = [nvvidconv1,nvvidconv2]

    print("Creating a caps filter element (enforce data format - maintain stream consistency and efficiency\n")
    caps1 = Gst.ElementFactory.make("capsfilter", "filter1")
    caps2 = Gst.ElementFactory.make("capsfilter", "filter2")
    if not caps1:
        sys.stderr.write("Unable to create caps \n")
    caps = [caps1, caps2]


    print("Creating EGLSink \n")
    sink1 = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer1")
    sink2 = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer2")
    if not sink1:
        sys.stderr.write(" Unable to create egl sink \n")
    sink=[sink1, sink2]
    if is_live:
        print("Atleast one of the sources is live")
        streammux.set_property('live-source', 1)

    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)

    for i in range(number_sources):
        tiler[i].set_property("rows",1)
        tiler[i].set_property("columns",1)
        tiler[i].set_property("width", TILED_OUTPUT_WIDTH)
        tiler[i].set_property("height", TILED_OUTPUT_HEIGHT)
        sink[i].set_property('async', False)
        sink[i].set_property('sync', 0)
        caps[i].set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))
 

    print("Adding elements to Pipeline \n")
    pipeline.add(tiler1,tiler2)
    pipeline.add(streamdemux)
    pipeline.add(nvvidconv1,nvvidconv2)
    pipeline.add(caps1,caps2)
    pipeline.add(sink1,sink2)


    print("Linking element ........ \n")
    streammux.link(streamdemux)
    for i in range(number_sources):
        print("demux source", i, "\n")
        srcpad1 = streamdemux.get_request_pad("src_%u"%i)
        if not srcpad1:
            sys.stderr.write(" Unable to get the src pad of streamdemux \n")
        sinkpad1 = nvvidconv[i].get_static_pad("sink")
        if not sinkpad1:
            sys.stderr.write(" Unable to get sink pad of nvvidconv \n")
        srcpad1.link(sinkpad1)
        #######################
    
        tiler[i].link(nvvidconv[i])
        nvvidconv[i].link(caps[i])
        caps[i].link(sink[i])


    # create an event loop and feed gstreamer bus mesages to it
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)

    # List the sources
    print("Now playing...")
    for i, source in enumerate(args):
        if (i != 0):
            print(i, ": ", source)

    print("Starting pipeline \n")
    # start play back and listed to events		
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    print("Exiting app\n")
    pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
