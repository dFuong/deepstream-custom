import tempfile
# Basic dependencies
from os import link, pipe
import os
import numpy as np
import pyds
import sys
from numpy.core.records import array
import numpy as np
from numpy.core.records import array
sys.path.append('../')
import time
from datetime import datetime
import math
import configparser
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GObject, Gst
from gi.repository import GLib
from gi.repository import GObject, Gst, GstRtspServer
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call
from common.FPS import GETFPS
from kafka import KafkaProducer
import json

CONFIG_FILE = 'config_tlt/dstest_tlt_config.txt'
CONFIG_ANALYTICS='config_pipeline/config_nvdsanalytics.txt'
CONFIG_TRACKER='config_pipeline/dstest_tracker_config.txt'

PGIE_CLASS_ID_PERSON = 0

OSD_PROCESS_MODE= 0
OSD_DISPLAY_TEXT= 1

FPS_streams={}
fps_streams={}

producer_0=KafkaProducer(bootstrap_servers='192.168.1.4:9092',value_serializer=lambda v: json.dumps(v).encode('utf-8'))
producer_1=KafkaProducer(bootstrap_servers='192.168.1.4:9092',value_serializer=lambda v: json.dumps(v).encode('utf-8'))

curTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad")
    caps=decoder_src_pad.get_current_caps()
    gststruct=caps.get_structure(0)
    gstname=gststruct.get_name()
    source_bin=data
    features=caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
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
    print("Creating source bin")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name="source-bin-%02d" %index
    print(bin_name)
    nbin=Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write("ERROR: Unable to create source bin")
        sys.exit(1)

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
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


def osd_sink_pad_buffer_probe(pad,info,u_data):
    frame_number=0
    #Intiallizing object counter with 0.
    obj_counter = {
        PGIE_CLASS_ID_PERSON:0
    }
    num_rects=0
    
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:

            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        frame_number=frame_meta.frame_num
        num_rects = frame_meta.num_obj_meta
        l_obj=frame_meta.obj_meta_list
        
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break

            obj_counter[obj_meta.class_id] += 1
            rect_para=obj_meta.rect_params
            top = int(rect_para.top)
            left = int(rect_para.left)
            width = int(rect_para.width)
            height = int(rect_para.height)

            if (frame_meta.pad_index==0):
                producer_0.send('test',{'@timestamp':'{}'.format(curTime),'Object in ROI source-0':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
            if (frame_meta.pad_index==1):
                producer_1.send('test1',{'@timestamp':'{}'.format(curTime),'Object in ROI source-1':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
            
            try: 
                l_obj=l_obj.next
            except StopIteration:
                break

        display_meta=pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_labels = 1
        py_nvosd_text_params = display_meta.text_params[0]
        
        # Extract coordinate

        print("--------------------------Source {} -----------------------------\n ".format(frame_meta.pad_index))
        py_nvosd_text_params.display_text = "Frame={}  Objects={}  Persons={} ".format(frame_number, num_rects, obj_counter[PGIE_CLASS_ID_PERSON])
        print("FPS-Source-{} = ".format(frame_meta.pad_index), FPS_streams["stream{}".format(frame_meta.pad_index)].calc_fps())
        fps_streams["stream{}".format(frame_meta.pad_index)].get_fps()
 
        # Now set the offsets where the string should appear
        py_nvosd_text_params.x_offset = 10
        py_nvosd_text_params.y_offset = 12

        # Font , font-color and font-size
        py_nvosd_text_params.font_params.font_name = "Serif"
        py_nvosd_text_params.font_params.font_size = 10
        # set(red, green, blue, alpha); set to White
        py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

        # Text background color
        py_nvosd_text_params.set_bg_clr = 1
        # set(red, green, blue, alpha); set to Black
        py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
        # Using pyds.get_string() to get display_text as string
        if SHOW_FRAMES:
            print(pyds.get_string(py_nvosd_text_params.display_text))
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
			
    return Gst.PadProbeReturn.OK	
def get_from_env(v, d):
  if v in os.environ and '' != os.environ[v]:
    return os.environ[v]
  else:
    return d
    
CODEC = get_from_env('CODEC', 'H265') 
BITRATE = get_from_env('BITRATE', '4000000')
RTSPOUTPUTPORTNUM = get_from_env('RTSPOUTPUTPORTNUM', '8554')
RTSPOUTPUTPATH = get_from_env('RTSPOUTPUTPATH', '/ds') # The output URL's path
RTSPOUTPUTPATH1 = get_from_env('RTSPOUTPUTPATH', '/ds1') # The output URL's path
IPADDR = get_from_env('IPADDR', '192.168.1.4') 
SHOW_FRAMES = 'no' != get_from_env('SHOW_FRAMES', 'yes') 
OUTPUT_WIDTH = int(get_from_env('OUTPUT_WIDTH', '1400')) # Output video width
OUTPUT_HEIGHT = int(get_from_env('OUTPUT_HEIGHT', '800')) # Output video height


def main(args):
    global FPS_streams

    if len(args) < 2:
        sys.stderr.write("usage: %s <uri1> [uri2] ... [uriN]\n" % args[0])
        sys.exit(1)
    number_sources=len(args)-1
    
    for i in range(number_sources):
        fps_streams["stream{0}".format(i)]=GETFPS(i)
        FPS_streams["stream{}".format(i)]=GETFPS(i)

    # Announce some useful info at startup
    print('\n\n\n\n')
    print('Using codec: %s, and bitrate: %s' % (CODEC, BITRATE))
    print('RTSP input streams (%d):' % (number_sources))

    print('RTSP output stream: "rtsp://%s:%s%s"' % (IPADDR, RTSPOUTPUTPORTNUM, RTSPOUTPUTPATH))
    print('\n\n\n\n')


    parent_folder_name = tempfile.mkdtemp()
    frame_count = {}
    saved_count = {}

    time.sleep(5)
    # Initialize GStreamer
    GObject.threads_init()
    Gst.init(None)

    print("Creating Pipeline \n")
    pipeline=Gst.Pipeline()
    is_live=False

    if not pipeline:
        sys.stderr.write("Unable to create Pipeline \n")
        sys.exit(1)
    
    print("Creating elements to recevice RTSP streams as the video input - Streammux\n")
    streammux=Gst.ElementFactory.make('nvstreammux',"Stream-muxer")
    if not streammux:
        sys.stderr.write("Unable to create NvStreamMux\n")
        sys.exit(1)
    
    print("Creating elements to separate out Streamdemux\n")
    streamdemux = Gst.ElementFactory.make("nvstreamdemux", "Stream-demuxer")
    if not streamdemux:
        sys.stderr.write(" Unable to create NvStreamdeMux \n")

    pipeline.add(streammux)
    for i in range(number_sources):
        print("Creating source_bin ",i," \n ")
        saved_count['stream_'+str(i)]=0
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
    
    print("Creating an element to do inferencing - Pgie-Nvinfer\n")
    pgie=Gst.ElementFactory.make("nvinfer",'primary-inference')
    if not pgie:
        sys.stderr.write("Unable to create Pgie \n")
    
    print("Creating an element to convert output video into RBGA format\n")
    nvvidconv1 = Gst.ElementFactory.make("nvvideoconvert", "convertor1")
    nvvidconv2 = Gst.ElementFactory.make("nvvideoconvert", "convertor2")
    if not nvvidconv1:
        sys.stderr.write("Unable to create nvvidconv\n")
    nvvidconv = [nvvidconv1, nvvidconv2]

    print("Creting nvdsananlytics \n")
    nvanalytics=Gst.ElementFactory.make('nvdsanalytics','analytics')
    if not nvanalytics:
        sys.stderr.write("Unable to create nvdsanalytics\n")
    
    print("Creating tracker \n")
    tracker=Gst.ElementFactory.make("nvtracker","tracker")
    if not tracker:
        sys.stderr.write("Unable to create tracker \n")
    
    print("Creating elements to draw boxes in the output video - nvosd - postosd\n")
    nvosd1 = Gst.ElementFactory.make("nvdsosd", "onscreendisplay1")
    nvosd2 = Gst.ElementFactory.make("nvdsosd", "onscreendisplay2")
    if not nvosd1:
        sys.stderr.write("Unable to creating nvdosd\n")
    nvosd = [nvosd1, nvosd2]

    nvvidconv_postosd1 = Gst.ElementFactory.make("nvvideoconvert", "convertor_postosd1")
    nvvidconv_postosd2 = Gst.ElementFactory.make("nvvideoconvert", "convertor_postosd2")
    if not nvvidconv_postosd1:
        sys.stderr.write("Unable to creat nvvidconv_postosd\n")
    nvvidconv_postosd = [nvvidconv_postosd1, nvvidconv_postosd2]

    print("Creating a caps filter element (enforce data format - maintain stream consistency and efficiency\n")
    caps1 = Gst.ElementFactory.make("capsfilter", "filter1")
    caps2 = Gst.ElementFactory.make("capsfilter", "filter2")
    if not caps1:
        sys.stderr.write("Unable to create caps \n")
    caps = [caps1, caps2]

    print("Creating to convert output video to H264/H265 for 4VL2\n")
    if CODEC=='H264':
        encoder1 = Gst.ElementFactory.make("nvv4l2h264enc", "encoder1")
        encoder2 = Gst.ElementFactory.make("nvv4l2h264enc", "encoder2")
        print("Creating H264 Encoder\n")
    elif CODEC=='H265':
        encoder1 = Gst.ElementFactory.make("nvv4l2h265enc", "encoder1")
        encoder2 = Gst.ElementFactory.make("nvv4l2h265enc", "encoder2")
        print("Creating H265 Encoder\n")
    if not encoder1:
        sys.stderr.write("ERROR: Unable to create encoder\n")
    encoder = [encoder1, encoder2]

    if is_aarch64():
        for i in range(number_sources):
            encoder[i].set_property('preset-level', 1)
            encoder[i].set_property('insert-sps-pps', 1)
            encoder[i].set_property('bufapi-version', 1)

    print("Creating an element to encapsulates video into RTP packets for RTSP streaming\n")
    if CODEC=='H264':
        rtppay1 = Gst.ElementFactory.make("rtph264pay", "rtppay1")
        rtppay2= Gst.ElementFactory.make("rtph264pay", "rtppay2")
        print("Creating H264 Rtppay\n")
    elif CODEC=='H265':
        rtppay1 = Gst.ElementFactory.make("rtph265pay", "rtppay1")
        rtppay2 = Gst.ElementFactory.make("rtph265pay", "rtppay2")
        print("Creating H265 Rtppay\n")
    if not rtppay1:
        sys.stderr.write("ERROR: Unable to create rtppay\n")
    rtppay = [rtppay1, rtppay2]
 
    print("Creating RTSP output stream sink  \n")
    sink1 = Gst.ElementFactory.make("udpsink", "udpsink1")
    sink2 = Gst.ElementFactory.make("udpsink", "udpsink2")
    if not sink1:
        sys.stderr.write("Unable to create udpsink\n")
    sink = [sink1, sink2]

    print("_____________Seting property_____________________ \n")

    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)
    nvanalytics.set_property('config-file',CONFIG_ANALYTICS)
    pgie.set_property('config-file-path', CONFIG_FILE)
    # UDP_MULTICAST_ADDRESS = '224.224.255.255'
    UDP_MULTICAST_PORT = [5400,5401]

    for i in range (number_sources):
        encoder[i].set_property('bitrate', int(BITRATE))
        caps[i].set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))
        nvosd[i].set_property('process-mode',OSD_PROCESS_MODE)
        nvosd[i].set_property('display-text',OSD_DISPLAY_TEXT)
        sink[i].set_property('host', '127.0.0.1')
        sink[i].set_property('async', False)
        sink[i].set_property('sync', 1)
        sink[i].set_property('port', UDP_MULTICAST_PORT[i])

    if not is_aarch64():
        # Use CUDA unified memory in the pipeline so frames
        # can be easily accessed on CPU in Python.
        mem_type = int(pyds.NVBUF_MEM_CUDA_UNIFIED)
        streammux.set_property("nvbuf-memory-type", mem_type)
        for i in range(number_sources):
            nvvidconv[i].set_property("nvbuf-memory-type", mem_type)
        # tiler.set_property("nvbuf-memory-type", mem_type)

   #Creating properties tracker
    config = configparser.ConfigParser()
    config.read(CONFIG_TRACKER)
    config.sections()

    for key in config['tracker']:
        if key == 'tracker-width' :
            tracker_width = config.getint('tracker', key)
            tracker.set_property('tracker-width', tracker_width)
        if key == 'tracker-height' :
            tracker_height = config.getint('tracker', key)
            tracker.set_property('tracker-height', tracker_height)
        if key == 'gpu-id' :
            tracker_gpu_id = config.getint('tracker', key)
            tracker.set_property('gpu_id', tracker_gpu_id)
        if key == 'll-lib-file' :
            tracker_ll_lib_file = config.get('tracker', key)
            tracker.set_property('ll-lib-file', tracker_ll_lib_file)
        if key == 'll-config-file' :
            tracker_ll_config_file = config.get('tracker', key)
            tracker.set_property('ll-config-file', tracker_ll_config_file)
        if key == 'enable-batch-process' :
            tracker_enable_batch_process = config.getint('tracker', key)
            tracker.set_property('enable_batch_process', tracker_enable_batch_process)
        if key == 'enable-past-frame' :
            tracker_enable_past_frame = config.getint('tracker', key)
            tracker.set_property('enable_past_frame', tracker_enable_past_frame)


    print("Creating Pipeline ........\n")
    pipeline.add(pgie)
    pipeline.add(streamdemux)
    pipeline.add(nvanalytics)
    pipeline.add(tracker)
    pipeline.add(nvvidconv1,nvvidconv2)
    pipeline.add(nvosd1, nvosd2)
    pipeline.add(nvvidconv_postosd1, nvvidconv_postosd2)
    pipeline.add(caps1, caps2)
    pipeline.add(encoder1, encoder2)
    pipeline.add(rtppay1, rtppay2)
    pipeline.add(sink1, sink2)


    print("Linking element ........ \n")
    streammux.link(pgie)
    pgie.link(nvanalytics)
    nvanalytics.link(tracker)
    tracker.link(streamdemux)
    
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
        
        nvvidconv[i].link(nvosd[i])
        nvosd[i].link(nvvidconv_postosd[i])
        nvvidconv_postosd[i].link(caps[i])
        caps[i].link(encoder[i])
        encoder[i].link(rtppay[i])
        rtppay[i].link(sink[i])


    print("The RTSP output stream element has been added to the pipeline, and linked")

    # create an event loop and feed gstreamer bus mesages to it
    print("Creating the event loop...")
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)
    

    server = GstRtspServer.RTSPServer.new()
    server.props.service = RTSPOUTPUTPORTNUM
    server.attach(None)
    
    factory1 = GstRtspServer.RTSPMediaFactory.new()
    factory2 = GstRtspServer.RTSPMediaFactory.new()
    factory1.set_launch( "( udpsrc name=pay0 port=%d buffer-size=524288 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 \" )" % (UDP_MULTICAST_PORT[0], CODEC))
    factory2.set_launch( "( udpsrc name=pay0 port=%d buffer-size=524288 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 \" )" % (UDP_MULTICAST_PORT[1], CODEC))
    factory1.set_shared(True)
    factory2.set_shared(True)
    server.get_mount_points().add_factory(RTSPOUTPUTPATH, factory1)
    server.get_mount_points().add_factory(RTSPOUTPUTPATH1, factory2)
    print("RTSP output stream service is ready")

    followingsinkpad1 = nvvidconv[0].get_static_pad("sink")
    followingsinkpad2 = nvvidconv[1].get_static_pad("sink")
    if not followingsinkpad1:
        sys.stderr.write("ERROR: Unable to get sink pad of nvosd\n")

    followingsinkpad1.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)
    followingsinkpad2.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # Start play back and listen to events
    print("\n\n\n\n*** Deepstream RTSP pipeline example is starting...\n\n\n\n")
    pipeline.set_state(Gst.State.PLAYING)
    try:
        # Run forever
        loop.run()
    except:
        sys.stderr.write("\n\n\n*** ERROR: main event loop exited!\n\n\n")

    # Attempt cleanup on error
    pipeline.set_state(Gst.State.NULL)


if __name__ == '__main__':
    sys.exit(main(sys.argv))

