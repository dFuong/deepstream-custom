 # Table of Contents

 - Introduction
 - Prerequisites
 - Install
 - How to use

## Introduction

- This repo is first custom deepstream:v5.1 (human detection) for **single source**
- Model can be trained by [TLT:v2.0_py3](https://ngc.nvidia.com/catalog/containers/nvidia:tlt-streamanalytics) or pretrained-model [PeopleNet](https://ngc.nvidia.com/catalog/models/nvidia:tlt_peoplenet)
- Model can be trained by [TAO-upgrade TLT](https://ngc.nvidia.com/catalog/containers/nvidia:tao:tao-toolkit-tf)

## Prerequisites

- DeepStreamSDK 5.1
- Python 3.6
- Gst-python

## Install

**Run with docker:**
- Docker pull for kernel architecture x86/amd64: `docker pull fsharp58/deepstream_custom:5.1_v1`
- Docker pull for kernel architecture x86/arm64 (jetson): `docker pull fsharp58/deepstream_custom:5.1.v1_l4t`
- Mount git-repo in docker follow: `-v <path to this directory> :/opt/nvidia/deepstream/deepstream/sources/python`

**Run with your host:**
- Follow README in branch: 2.0.1


**Dependencies**
------------
 `$sudo apt-get update`
 
Kafka:
 ------
    $ sudo apt-get install libglib2.0 libglib2.0-dev
    $ sudo apt-get install libjansson4  libjansson-dev
    $ sudo apt-get install librdkafka1=0.11.3-1build1

- Set up Kafka following docker:[Kafka-docker](https://forums.developer.nvidia.com/t/using-kafka-protocol-for-retrieving-data-from-a-deepstream-pipeline/67626/14)
- Set up Kafka following Kafka-enviroment:[Kafka-enviroment](https://kafka.apache.org/quickstart)


## How to use

**SETUP**

  1.Use --proto-lib line option to set the path of adaptor library.

    Adaptor library can be found at /opt/nvidia/deepstream/deepstream-<version>/lib
    kafka lib           - libnvds_kafka_proto.so

  2.Use --conn-str line option as required to set connection to backend server.

    For Azure           - Full Azure connection string
    For Kafka           - Connection string of format:  host;port;topic
    For Amqp            - Connection string of format:  host;port;username. Password to be provided in cfg_amqp.txt

    Provide connection string under quotes. e.g. --conn-str="host;port;topic"

  3.Use --topic line option to provide message topic (optional).

    Kafka message adaptor also has the topic param embedded within the connection string format
    In that case, "topic" from command line should match the topic within connection string

  4.Use --schema line option to select the message schema (optional).

    Json payload to send to cloud can be generated using different message schemas.
    schema = 0; Full message schema with separate payload per object (Default)
    schema = 1; Minimal message with multiple objects in single payload.
    Refer user guide to get more details about message schema.

  5.Use --no-display to disable display.

  6.Use --cfg-file line option to set adaptor configuration file.
  
    This is optional if connection string has all relevent information.

    For kafka: use cfg_kafka.txt as a reference.
    This file is used to define the parition key field to be used while sending messages to the
    kafka broker. Refer Kafka Protocol Adaptor section in the DeepStream 4.0 Plugin Manual for
    more details about using this config option. The partition-key setting within the cfg_kafka.txt
    should be set based on the schema type selected using the --schema option. Set this to
    "sensor.id" in case of Full message schema, and to "sensorId" in case of Minimal message schema
    
  7.Enable logging:
       Go through the README to setup & enable logs for the messaging libraries kafka.
        $ cat ../../../tools/nvds_logger/README

**To run:**
```
python3 deepstream_test.py file:<path to video(H-265)> 
python3 deepstream_test.py rtsp:// 
```


