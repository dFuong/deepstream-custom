from distutils.core import setup
setup (name = 'libnvds_msgbroker',
        version ='1.0',
        description = """Install precompiled DeepStream Python bindings for msg_meta metadata extension""",
        packages=[''],
        package_data={'': ['libnvds_msgbroker.so']},
        )