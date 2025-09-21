from setuptools import setup, find_packages

setup(
    name="godadder",
    version="0.1.0",
    description="Adomain generator and checking app",
    author="Gideon Bar",
    author_email="gideonbar@gmail.com",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "ipython",
        "ipykernel",
        "jupyter",
        "requests",
        "pandas",
        "numpy",
        "matplotlib",
        "pillow",
        "exifread",
        "pyhocon",
        "pydantic-ai",
    ],
    python_requires=">=3.11",
)
