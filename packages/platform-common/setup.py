from setuptools import setup, find_packages

setup(
    name="platform-common",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "pydantic>=2.0.0",
    ],
)
