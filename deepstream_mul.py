from os import link, pipe
import sys
import numpy as np
from numpy.core.records import array
sys.path.append('../')
import gi
import configparser
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst
from gi.repository import GLib
from ctypes import *
import time
from datetime import datetime
import sys
import math
from optparse import OptionParser
import platform
import matplotlib.path as mplPath
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call
from common.FPS import GETFPS
from common.utils import long_to_int
import pyds

from kafka import KafkaProducer
import json

fps_streams={}
FPS_streams=None
past_tracking_meta=[0]
saved_count={}
OUTPUT_VIDEO_NAME="./out.mp4"

MAX_DISPLAY_LEN=64
MAX_TIME_STAMP_LEN=32
global PGIE_CLASS_ID_PERSON
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3

MUXER_OUTPUT_WIDTH=1920
MUXER_OUTPUT_HEIGHT=1080

MUXER_BATCH_TIMEOUT_USEC=4000000
TILED_OUTPUT_WIDTH=1280
TILED_OUTPUT_HEIGHT=720
GST_CAPS_FEATURES_NVMM="memory:NVMM"
OSD_PROCESS_MODE= 0
OSD_DISPLAY_TEXT= 1
pgie_classes_str=  ["Vehicle", "TwoWheeler", "Person", "RoadSign"]
schema_type = 0
frame_number = 0
proto_lib ='/opt/nvidia/deepstream/deepstream-5.1/lib/libnvds_kafka_proto.so'
conn_str="192.168.1.3;9092;test"
cfg_file = 'config_broker/cfg_kafka.txt'
topic = "test"
no_display = False

producer_0=KafkaProducer(bootstrap_servers='192.168.1.3:9092',value_serializer=lambda v: json.dumps(v).encode('utf-8'))
    # producer = KafkaProducer(value_serializer=lambda v: json.dumps(v).encode('utf-8'))
producer_1=KafkaProducer(bootstrap_servers='192.168.1.3:9092',value_serializer=lambda v: json.dumps(v).encode('utf-8'))
    # producer = KafkaProducer(value_serializer=lambda v: json.dumps(v).encode('utf-8'))
curTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S")

roi_poly_1=mplPath.Path(np.array([[280,643],[579,634],[642,913],[45,828]]))
roi_line_1=mplPath.Path(np.array([[190,690],[600,690],[600,680],[180,680]]))

roi_poly=mplPath.Path(np.array([[450,360],[1400,360],[1400,870],[450,870]]))
roi_line=mplPath.Path(np.array([[450,750],[1400,750],[1400,600],[450,600]]))

point_A=[450,650]
point_B=[1400,651]

point_A_1=[189,688]
point_B_1=[601,689] 

PGIE_CONFIG_FILE="config_pipeline/dstest4_pgie_config.txt"
# MSCONV_CONFIG_FILE="config_pipeline/dstest4_msgconv_config.txt"

def param_a (a,b):
    T = int((b[1]-a[1])/(b[0]-a[0]))
    # H = float((a[0]*T) - a[1])
    return T

a_init=param_a(point_A,point_B)
b_init=param_a(point_A_1,point_B_1)


# Callback function for deep-copying an NvDsEventMsgMeta struct
def meta_copy_func(data,user_data):
    # Cast data to pyds.NvDsUserMeta
    user_meta=pyds.NvDsUserMeta.cast(data)
    src_meta_data=user_meta.user_meta_data
    # Cast src_meta_data to pyds.NvDsEventMsgMeta
    srcmeta=pyds.NvDsEventMsgMeta.cast(src_meta_data)

    dstmeta_ptr=pyds.memdup(pyds.get_ptr(srcmeta), sys.getsizeof(pyds.NvDsEventMsgMeta))
    # Cast the duplicated memory to pyds.NvDsEventMsgMeta
    dstmeta=pyds.NvDsEventMsgMeta.cast(dstmeta_ptr)

    # Duplicate contents of ts field. Note that reading srcmeat.ts
    # returns its C address. This allows to memory operations to be
    # performed on it.
    dstmeta.ts=pyds.memdup(srcmeta.ts, MAX_TIME_STAMP_LEN+1)

   
    # dstmeta.sensorStr=pyds.get_string(srcmeta.sensorStr)

    if(srcmeta.objSignature.size>0):
        dstmeta.objSignature.signature=pyds.memdup(srcmeta.objSignature.signature,srcMeta.objSignature.size)
        dstmeta.objSignature.size = srcmeta.objSignature.size;

    if(srcmeta.extMsgSize>0):
        if(srcmeta.objType==pyds.NvDsObjectType.NVDS_OBJECT_TYPE_PERSON):
            srcobj = pyds.NvDsPersonObject.cast(srcmeta.extMsg);
            obj = pyds.alloc_nvds_person_object()
            dstmeta.extMsg = obj;
            dstmeta.extMsgSize = sys.getsizeof(pyds.NvDsVehicleObject);

    return dstmeta

# Callback function for freeing an NvDsEventMsgMeta instance
def meta_free_func(data,user_data):
    user_meta=pyds.NvDsUserMeta.cast(data)
    srcmeta=pyds.NvDsEventMsgMeta.cast(user_meta.user_meta_data)

    # pyds.free_buffer takes C address of a buffer or frees the memory
    # It's a NOP if the address is NULL
    pyds.free_buffer(srcmeta.ts)
    pyds.free_buffer(srcmeta.sensorStr)

    if(srcmeta.objSignature.size > 0):
        pyds.free_buffer(srcmeta.objSignature.signature);
        srcmeta.objSignature.size = 0

    if(srcmeta.extMsgSize > 0):
        if(srcmeta.objType == pyds.NvDsObjectType.NVDS_OBJECT_TYPE_PERSON):
            obj = pyds.NvDsPersonObject.cast(srcmeta.extMsg);
        pyds.free_gbuffer(srcmeta.extMsg);
        srcmeta.extMsgSize = 0;


def generate_event_msg_meta(data, class_id):
    meta =pyds.NvDsEventMsgMeta.cast(data)
    meta.ts = pyds.alloc_buffer(MAX_TIME_STAMP_LEN + 1)
    pyds.generate_ts_rfc3339(meta.ts, MAX_TIME_STAMP_LEN)


    if(class_id == PGIE_CLASS_ID_PERSON):
        meta.type =pyds.NvDsEventType.NVDS_EVENT_ENTRY
        meta.objType = pyds.NvDsObjectType.NVDS_OBJECT_TYPE_PERSON;
        meta.objClassId = PGIE_CLASS_ID_PERSON
        obj = pyds.alloc_nvds_person_object()
        meta.extMsg = obj
        meta.extMsgSize = sys.getsizeof(pyds.NvDsPersonObject)
    return meta

def tiler_src_pad_buffer_probe(pad,info,u_data):
    frame_number=0
    num_rects=0
    global f
    global FPS_streams
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return


    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
  
    l_frame = batch_meta.frame_meta_list
    while l_frame:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
         
        except StopIteration:
            break

        frame=frame_meta.frame_num
        l_obj=frame_meta.obj_meta_list

        num_rects = frame_meta.num_obj_meta
        obj_counter = {
            PGIE_CLASS_ID_VEHICLE: 0,
            PGIE_CLASS_ID_PERSON: 0,
            PGIE_CLASS_ID_BICYCLE: 0,
            PGIE_CLASS_ID_ROADSIGN: 0
        }
        # print("------------------------------------------------------------------------------------------------------")
        while l_obj:
            try: 
                # Note that l_obj.data needs a cast to pyds.NvDsObjectMeta
                # The casting is done by pyds.NvDsObjectMeta.cast()
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
                
            except StopIteration:
                break
            obj_counter[obj_meta.class_id] += 1
            l_user_meta = obj_meta.obj_user_meta_list
            rect_para=obj_meta.rect_params
            frame_number=frame
            top_left=(rect_para.left, rect_para.top)
            bottom_left=(rect_para.left+1, rect_para.top +rect_para.height)
            top_right=(rect_para.left + rect_para.width, rect_para.top)
            bottom_right=(rect_para.left+rect_para.width +1, rect_para.top +rect_para.height)

            top = int(rect_para.top)
            left = int(rect_para.left)
            width = int(rect_para.width)
            height = int(rect_para.height)
            
            if (frame_meta.pad_index==0 and obj_meta.class_id==2 ):
                if (roi_poly.contains_point(top_left) or roi_poly.contains_point(top_right) or roi_poly.contains_point(bottom_right) or roi_poly.contains_point(bottom_left)):
                    print("\n----------------------Object in ROI {}------------------\n".format(frame_meta.pad_index))
                    print("Frame_number", frame_number)
                    print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                    producer_0.send('test',{'@timestamp':'{}'.format(curTime),'Object in ROI source-0':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
                
                
                if (roi_line.contains_point(top_left) or roi_line.contains_point(top_right) or roi_line.contains_point(bottom_right) or roi_line.contains_point(bottom_left)):
                    a_left=param_a(top_left, bottom_left)
                    a_right=param_a(top_right, bottom_right)
                    if ( a_init!=a_left or a_init!=a_right):
                        print("\n----------------------Object crossing Line {}------------------\n".format(frame_meta.pad_index))
                        print("Frame_number", frame_number)
                        print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                        producer_0.send('test',{'@timestamp':'{}'.format(curTime),'Object crossing Line source-0':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
            
            if (frame_meta.pad_index==1 and obj_meta.class_id==2 ):
                if (roi_poly_1.contains_point(top_left) or roi_poly_1.contains_point(top_right) or roi_poly_1.contains_point(bottom_right) or roi_poly_1.contains_point(bottom_left)):
                    print("\n----------------------Object in ROI {}------------------\n".format(frame_meta.pad_index))
                    print("Frame_number", frame_number)
                    print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                    producer_1.send('test1',{'@timestamp':'{}'.format(curTime),'Object in ROI source-1':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
                
                if (roi_line_1.contains_point(top_left) or roi_line_1.contains_point(top_right) or roi_line_1.contains_point(bottom_right) or roi_line_1.contains_point(bottom_left)):
                    a_left=param_a(top_left, bottom_left)
                    a_right=param_a(top_right, bottom_right)
                    if ( b_init!=a_left or b_init!=a_right):
                        print("\n----------------------Object crossing Line {}------------------\n".format(frame_meta.pad_index))
                        print("Frame_number", frame_number)
                        print(f"ID = {obj_meta.object_id} class id = {obj_meta.class_id}")
                        producer_1.send('test1',{'@timestamp':'{}'.format(curTime),'Object crossing Line source-1':{'Frame_number':'{}'.format(frame_number), 'ID':"{}".format(obj_meta.object_id), 'Coordinate':{'x':'{}'.format(top), 'y':'{}'.format(left), 'width':'{}'.format(width), 'height':'{}'.format(height)}}})
            # print(f"ID:{obj_meta.object_id} class id:{obj_meta.class_id} conf:{obj_meta.confidence} unique_component_id:{obj_meta.unique_component_id}")

            while l_user_meta:
                try:
                    user_meta = pyds.NvDsUserMeta.cast(l_user_meta.data)
                    if user_meta.base_meta.meta_type == pyds.nvds_get_user_meta_type("NVIDIA.DSANALYTICSOBJ.USER_META"):             
                        user_meta_data = pyds.NvDsAnalyticsObjInfo.cast(user_meta.user_meta_data)

                except StopIteration:
                    break

                try:
                    l_user_meta = l_user_meta.next
                except StopIteration:
                    break
            try: 
                l_obj=l_obj.next
            except StopIteration:
                break
        
        l_user = frame_meta.frame_user_meta_list
        while l_user:
            try:
                user_meta = pyds.NvDsUserMeta.cast(l_user.data)
                if user_meta.base_meta.meta_type == pyds.nvds_get_user_meta_type("NVIDIA.DSANALYTICSFRAME.USER_META"):
                    user_meta_data = pyds.NvDsAnalyticsFrameMeta.cast(user_meta.user_meta_data)
            
            except StopIteration:
                break
            try:
                l_user = l_user.next
            except StopIteration:
                break
        # print("Frame Number=", frame_number, "stream id=", frame_meta.pad_index, "Number of Objects=",num_rects,"Face_count=",obj_counter[PGIE_CLASS_ID_FACE],"Person_count=",obj_counter[PGIE_CLASS_ID_PERSON])
        # Get frame rate through this probe
    
        # fps_streams["stream{0}".format(frame_meta.pad_index)].get_fps()
        # print("FPS = ",FPS_streams.calc_fps())
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
        # print("------------------------------------------------------------------------------------------------------")

    return Gst.PadProbeReturn.OK	


def cb_newpad(decodebin, decoder_src_pad,data):
    print("In cb_newpad\n")
    caps=decoder_src_pad.get_current_caps()
    gststruct=caps.get_structure(0)
    gstname=gststruct.get_name()
    source_bin=data
    features=caps.get_features(0)
    
    # Need to check if the pad created by the decodebin is for video or not
    # audio.
    print("gstname=",gstname)
    if(gstname.find("video")!=-1):
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        print("features=",features)
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad=source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
        else:
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")

def decodebin_child_added(child_proxy,Object,name,user_data):
    print("Decodebin child added:", name, "\n")
    if(name.find("decodebin") != -1):
        Object.connect("child-added",decodebin_child_added,user_data)

def create_source_bin(index,uri):
    print("Creating source bin")

    bin_name="source-bin-%02d" %index
    print(bin_name)
    nbin=Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")


    uri_decode_bin=Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri",uri)

    uri_decode_bin.connect("pad-added",cb_newpad,nbin)
    uri_decode_bin.connect("child-added",decodebin_child_added,nbin)

  
    Gst.Bin.add(nbin,uri_decode_bin)
    bin_pad=nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin

def main(args):
    # registering callbacks
    pyds.register_user_copyfunc(meta_copy_func)
    pyds.register_user_releasefunc(meta_free_func)

    global FPS_streams
    FPS_streams=GETFPS(0)
    # past_tracking_meta[0]=1
    # Check input arguments

    if len(args) < 2:
        sys.stderr.write("usage: %s <uri1> [uri2] ... [uriN]\n" % args[0])
        sys.exit(1)

    for i in range(0,len(args)-1):
        fps_streams["stream{0}".format(i)]=GETFPS(i)
    number_sources=len(args)-1

    # Storard GStreamer initialization
    GObject.threads_init()
    Gst.init(None)

    # Create gstreamer elements */
    # Create Pipeline element that will form a connection of other elements
    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    is_live = False

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")
    print("Creating streamux \n ")

    # Create nvstreammux instance to form batches from one or more sources.
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    # streammux = Gst.ElementFactory.make("nvmultistreamtiler", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

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

    print("Creating Pgie \n ")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie \n")
    print("Creating tiler \n ")
    tiler=Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
    if not tiler:
        sys.stderr.write(" Unable to create tiler \n")
    print("Creating nvvidconv \n ")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")

    if not nvvidconv:
        sys.stderr.write(" Unable to create nvvidconv \n")
    print("Creting nvdsananlytics \n")
    nvanalytics=Gst.ElementFactory.make('nvdsanalytics','analytics')
    if not nvanalytics:
        sys.stderr.write("Unable to create nvdsanalytics\n")
    print("Creating nvms-converter\n")
    # msgconv=Gst.ElementFactory.make("nvmsgconv", "nvmsg-converter")
    # if not msgconv:
    #     sys.stderr.write(" Unable to create msgconv \n")
    # print("Creating msgbroker \n")
    # msgbroker=Gst.ElementFactory.make("nvmsgbroker", "nvmsg-broker")
    # if not msgbroker:
    #     sys.stderr.write(" Unable to create msgbroker \n")
    print("Creating tee \n")
    tee=Gst.ElementFactory.make("tee", "nvsink-tee")
    if not tee:
        sys.stderr.write(" Unable to create tee \n")
    print("Creating nvtee-queue1 &queue2 \n")
    queue1=Gst.ElementFactory.make("queue", "nvtee-que1")
    if not queue1:
        sys.stderr.write(" Unable to create queue1 \n")
    queue2=Gst.ElementFactory.make("queue", "nvtee-que2")
    if not queue2:
        sys.stderr.write(" Unable to create queue2 \n")
    print("Creating tracker \n")
    tracker=Gst.ElementFactory.make("nvtracker","tracker")
    if not tracker:
        sys.stderr.write("Unable to create tracker \n")
    print("Creating nvosd \n ")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
 

    if not nvosd :
        sys.stderr.write(" Unable to create nvosd \n")
    nvosd.set_property('process-mode',OSD_PROCESS_MODE)
    nvosd.set_property('display-text',OSD_DISPLAY_TEXT)
  

    if(is_aarch64()):
        print("Creating transform \n ")
        transform=Gst.ElementFactory.make("nvegltransform", "nvegl-transform")
        if not transform:
            sys.stderr.write(" Unable to create transform \n")

    print("Creating EGLSink \n")
    sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
    # sink = Gst.ElementFactory.make("fakesink", "nvvideo-renderer")
    # sink = Gst.ElementFactory.make("filesink", "filesink")

    if not sink:
        sys.stderr.write(" Unable to create egl sink \n")

    if is_live:
        print("Atleast one of the sources is live")
        streammux.set_property('live-source', 1)

    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)
    nvanalytics.set_property('config-file',"config_pipeline/config_nvdsanalytics.txt")
    pgie.set_property('config-file-path', PGIE_CONFIG_FILE)
    pgie_batch_size=pgie.get_property("batch-size")
    # msgconv.set_property('config',MSCONV_CONFIG_FILE)
    # msgconv.set_property('payload-type', schema_type)
    # msgbroker.set_property('proto-lib', proto_lib)
    # msgbroker.set_property('conn-str', conn_str)

    # if cfg_file is not None:
    #     msgbroker.set_property('config', cfg_file)
    # if topic is not None:
    #     msgbroker.set_property('topic', topic)
    # msgbroker.set_property('sync', False)

    if(pgie_batch_size != number_sources):
        print("WARNING: Overriding infer-config batch-size",pgie_batch_size," with number of sources ", number_sources," \n")
        pgie.set_property("batch-size",number_sources)

    tiler_rows=int(math.sqrt(number_sources))
    tiler_columns=int(math.ceil((1.0*number_sources)/tiler_rows))
    tiler.set_property("rows",tiler_rows)
    tiler.set_property("columns",tiler_columns)
    tiler.set_property("width", TILED_OUTPUT_WIDTH)
    tiler.set_property("height", TILED_OUTPUT_HEIGHT)
    sink.set_property("qos",0)
    sink.set_property("sync", 0)
    # sink.set_property("async", 0)

    #Creating properties tracker
    config = configparser.ConfigParser()
    config.read('config_pipeline/dstest4_tracker_config.txt')
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


    print("Adding elements to Pipeline \n")
    pipeline.add(pgie)
    pipeline.add(nvanalytics)
    pipeline.add(tracker)
    pipeline.add(tiler)
    pipeline.add(tee)
    pipeline.add(queue1)
    pipeline.add(queue2)
    pipeline.add(nvvidconv)
    # pipeline.add(msgconv) 
    # pipeline.add(msgbroker)
    pipeline.add(nvosd)
    if is_aarch64():
        pipeline.add(transform)
    pipeline.add(sink)

    print("Linking elements in the Pipeline \n")
    streammux.link(pgie)
    pgie.link(tracker)
    tracker.link(nvvidconv)
    nvvidconv.link(nvanalytics)
    nvanalytics.link(tiler)
    tiler.link(nvosd)
    nvosd.link(queue1)
    # queue1.link(msgconv)
    # msgconv.link(msgbroker)
    if is_aarch64():
        queue1.link(transform)
        # nvosd.link(transform)
        transform.link(sink)
    else:
        queue1.link(sink)
        # nvosd.link(sink) 

    # sink_pad=queue1.get_static_pad("sink")
    # tee_msg_pad=tee.get_request_pad('src_%u')
    # tee_render_pad=tee.get_request_pad("src_%u")
    # if not tee_msg_pad or not tee_render_pad:
    #     sys.stderr.write("Unable to get request pads\n")
    # tee_msg_pad.link(sink_pad)
    # sink_pad=queue2.get_static_pad("sink")
    # tee_render_pad.link(sink_pad)

    # create an event loop or feed gstreamer bus mesages to it
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)
    # tiler_src_pad=pgie.get_static_pad("sink")
    # tiler_src_pad=nvosd.get_static_pad("sink")
    tiler_src_pad=tiler.get_static_pad('sink')

    if not tiler_src_pad:
        sys.stderr.write(" Unable to get src pad \n")
    else:
        tiler_src_pad.add_probe(Gst.PadProbeType.BUFFER, tiler_src_pad_buffer_probe, 0)

    # List the sources
    print("Now playing...")
    for i, source in enumerate(args):
        if (i != 0):
            print(i, ": ", source)

    print("Starting pipeline \n")

    # start play back or listed to events
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    pyds.unset_callback_funcs()
    pipeline.set_state(Gst.State.NULL)

    
if __name__ == '__main__':
    sys.exit(main(sys.argv))
