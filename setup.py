from setuptools import setup, find_packages

setup(
    name="synthetic-email-generator",
    version="0.1.0",
    description="Adaptive Synthetic Email Generation with Automated Evaluation",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "pandas>=2.0",
        "numpy>=1.24",
        "scikit-learn>=1.3",
        "torch>=2.0",
        "transformers>=4.30",
        "sentence-transformers>=2.2",
        "matplotlib>=3.7",
        "seaborn>=0.12",
        "plotly>=5.15",
        "networkx>=3.1",
        "streamlit>=1.28",
        "pyyaml>=6.0",
        "scipy>=1.10",
    ],
)
