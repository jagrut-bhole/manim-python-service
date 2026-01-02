# validator.py
import re

DANGEROUS_IMPORTS = [
    'os', 'sys', 'subprocess', 'shutil', 'pathlib',
    'requests', 'urllib', 'socket', 'pickle',
    'eval', 'exec', 'compile', '__import__',
]

ALLOWED_IMPORTS = [
    'manim', 'numpy', 'math', 'random'
]

# Animations that have known compatibility issues
PROBLEMATIC_ANIMATIONS = [
    'Rotating(',  # Known to cause issues with certain parameters
]

# Features that require external dependencies
LATEX_DEPENDENT = [
    'MathTex(',
    'Tex(',
]

def validate_code(code: str) -> tuple[bool, str]:
    """
    Validate Manim code for security
    Returns: (is_valid, error_message)
    """
    
    # Check if code contains 'from manim import'
    if 'from manim import' not in code:
        return False, "Code must start with 'from manim import *'"
    
    # Check for dangerous imports
    for dangerous in DANGEROUS_IMPORTS:
        patterns = [
            f'import {dangerous}',
            f'from {dangerous}',
            f'__import__("{dangerous}")',
            f"__import__('{dangerous}')",
        ]
        for pattern in patterns:
            if pattern in code:
                return False, f"Dangerous import detected: {dangerous}"
    
    # Check for dangerous functions
    dangerous_funcs = ['eval(', 'exec(', 'compile(', 'open(']
    for func in dangerous_funcs:
        if func in code:
            return False, f"Dangerous function detected: {func}"
    
    # Check if it has a Scene class (either Scene or ThreeDScene)
    has_scene = '(Scene)' in code or '(ThreeDScene)' in code
    if 'class ' not in code or not has_scene:
        return False, "Code must contain a Scene or ThreeDScene class"
    
    # Check if it has construct method
    if 'def construct(self):' not in code:
        return False, "Scene class must have a construct() method"
    
    # Warn about problematic animations (but don't fail - let manim handle it)
    for anim in PROBLEMATIC_ANIMATIONS:
        if anim in code:
            print(f"Warning: Code uses potentially problematic animation: {anim}")
    
    # Warn about LaTeX-dependent features
    for latex_feat in LATEX_DEPENDENT:
        if latex_feat in code:
            print(f"Warning: Code uses {latex_feat} which requires LaTeX to be installed (MiKTeX on Windows)")
            print(f"  Consider using Text() with Unicode symbols instead for simple labels")
    
    return True, ""

def extract_scene_name(code: str) -> str:
    """
    Extract the Scene class name from code
    Returns: class name or None
    """
    # Check for ThreeDScene first
    match = re.search(r'class\s+(\w+)\s*\(ThreeDScene\)', code)
    if match:
        return match.group(1)
    
    # Check for regular Scene
    match = re.search(r'class\s+(\w+)\s*\(Scene\)', code)
    if match:
        return match.group(1)
    
    return None