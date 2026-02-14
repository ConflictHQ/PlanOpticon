"""Prompt templates for LLM-based content analysis."""
import json
import logging
import os
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

class PromptTemplate:
    """Template manager for LLM prompts."""
    
    def __init__(
        self, 
        templates_dir: Optional[Union[str, Path]] = None,
        default_templates: Optional[Dict[str, str]] = None
    ):
        """
        Initialize prompt template manager.
        
        Parameters
        ----------
        templates_dir : str or Path, optional
            Directory containing template files
        default_templates : dict, optional
            Default templates to use
        """
        self.templates_dir = Path(templates_dir) if templates_dir else None
        self.templates = {}
        
        # Load default templates
        if default_templates:
            self.templates.update(default_templates)
        
        # Load templates from directory if provided
        if self.templates_dir and self.templates_dir.exists():
            self._load_templates_from_dir()
    
    def _load_templates_from_dir(self) -> None:
        """Load templates from template directory."""
        if not self.templates_dir:
            return
            
        for template_file in self.templates_dir.glob("*.txt"):
            template_name = template_file.stem
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    template_content = f.read()
                self.templates[template_name] = template_content
                logger.debug(f"Loaded template: {template_name}")
            except Exception as e:
                logger.warning(f"Error loading template {template_name}: {str(e)}")
    
    def get_template(self, template_name: str) -> Optional[Template]:
        """
        Get template by name.
        
        Parameters
        ----------
        template_name : str
            Template name
            
        Returns
        -------
        Template or None
            Template object if found, None otherwise
        """
        if template_name not in self.templates:
            logger.warning(f"Template not found: {template_name}")
            return None
            
        return Template(self.templates[template_name])
    
    def format_prompt(self, template_name: str, **kwargs) -> Optional[str]:
        """
        Format prompt with provided parameters.
        
        Parameters
        ----------
        template_name : str
            Template name
        **kwargs : dict
            Template parameters
            
        Returns
        -------
        str or None
            Formatted prompt if template exists, None otherwise
        """
        template = self.get_template(template_name)
        if not template:
            return None
            
        try:
            return template.safe_substitute(**kwargs)
        except Exception as e:
            logger.error(f"Error formatting template {template_name}: {str(e)}")
            return None
    
    def add_template(self, template_name: str, template_content: str) -> None:
        """
        Add or update template.
        
        Parameters
        ----------
        template_name : str
            Template name
        template_content : str
            Template content
        """
        self.templates[template_name] = template_content
    
    def save_template(self, template_name: str) -> bool:
        """
        Save template to file.
        
        Parameters
        ----------
        template_name : str
            Template name
            
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        if not self.templates_dir:
            logger.error("Templates directory not set")
            return False
            
        if template_name not in self.templates:
            logger.warning(f"Template not found: {template_name}")
            return False
            
        try:
            self.templates_dir.mkdir(parents=True, exist_ok=True)
            template_path = self.templates_dir / f"{template_name}.txt"
            
            with open(template_path, "w", encoding="utf-8") as f:
                f.write(self.templates[template_name])
                
            logger.debug(f"Saved template: {template_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving template {template_name}: {str(e)}")
            return False

# Default prompt templates
DEFAULT_TEMPLATES = {
    "content_analysis": """
    Analyze the provided video content and extract key information:

    TRANSCRIPT:
    $transcript

    VISUAL ELEMENTS (if available):
    $visual_elements

    Please extract and organize the following:
    - Main topics and themes
    - Key points for each topic
    - Important details or facts
    - Action items or follow-ups
    - Relationships between concepts
    
    Format the output as structured markdown.
    """,
    
    "diagram_extraction": """
    Analyze the following image that contains a diagram, whiteboard content, or other visual information.
    
    Extract and convert this visual information into a structured representation.
    
    If it's a flowchart, process diagram, or similar structured visual:
    - Identify the components and their relationships
    - Preserve the logical flow and structure
    - Convert it to mermaid diagram syntax
    
    If it's a whiteboard with text, bullet points, or unstructured content:
    - Extract all text elements
    - Preserve hierarchical organization if present
    - Maintain any emphasized or highlighted elements
    
    Image context: $image_context
    
    Return the results as markdown with appropriate structure.
    """,
    
    "action_item_detection": """
    Review the following transcript and identify all action items, commitments, or follow-up tasks.
    
    TRANSCRIPT:
    $transcript
    
    For each action item, extract:
    - The specific action to be taken
    - Who is responsible (if mentioned)
    - Any deadlines or timeframes
    - Priority level (if indicated)
    - Context or additional details
    
    Format the results as a structured list of action items.
    """,
    
    "content_summary": """
    Provide a concise summary of the following content:

    $content

    The summary should:
    - Capture the main points and key takeaways
    - Be approximately 3-5 paragraphs
    - Focus on the most important information
    - Maintain a neutral, objective tone

    Format the summary as clear, readable text.
    """,

    "summary_generation": """
    Generate a comprehensive summary of the following transcript content.

    CONTENT:
    $content

    Provide a well-structured summary that:
    - Captures the main topics discussed
    - Highlights key decisions or conclusions
    - Notes any important context or background
    - Is 3-5 paragraphs long

    Write in clear, professional prose.
    """,

    "key_points_extraction": """
    Extract the key points from the following content.

    CONTENT:
    $content

    Return a JSON array of key point objects. Each object should have:
    - "point": the key point (1-2 sentences)
    - "topic": category or topic area (optional)
    - "details": supporting details (optional)

    Example format:
    [
      {"point": "The system uses microservices architecture", "topic": "Architecture", "details": "Each service handles a specific domain"},
      {"point": "Migration is planned for Q2", "topic": "Timeline", "details": null}
    ]

    Return ONLY the JSON array, no additional text.
    """,

    "entity_extraction": """
    Extract all notable entities (people, concepts, technologies, organizations, time references) from the following content.

    CONTENT:
    $content

    Return a JSON array of entity objects:
    [
      {"name": "entity name", "type": "person|concept|technology|organization|time", "description": "brief description"}
    ]

    Return ONLY the JSON array, no additional text.
    """,

    "relationship_extraction": """
    Given the following content and entities, identify relationships between them.

    CONTENT:
    $content

    KNOWN ENTITIES:
    $entities

    Return a JSON array of relationship objects:
    [
      {"source": "entity A", "target": "entity B", "type": "relationship type (e.g., uses, manages, depends_on, created_by, part_of)"}
    ]

    Return ONLY the JSON array, no additional text.
    """,

    "diagram_analysis": """
    Analyze the following text extracted from a diagram or visual element.

    DIAGRAM TEXT:
    $diagram_text

    Identify:
    1. The type of diagram (flowchart, architecture, sequence, etc.)
    2. The main components and their roles
    3. The relationships between components
    4. Any data flows or process steps

    Return a JSON object:
    {
      "diagram_type": "type",
      "components": ["list of components"],
      "relationships": ["component A -> component B: description"],
      "summary": "brief description of what the diagram shows"
    }

    Return ONLY the JSON object, no additional text.
    """,

    "mermaid_generation": """
    Convert the following diagram information into valid Mermaid diagram syntax.

    Diagram Type: $diagram_type
    Text Content: $text_content
    Analysis: $semantic_analysis

    Generate a Mermaid diagram that accurately represents the visual structure.
    Use the appropriate Mermaid diagram type (graph, sequenceDiagram, classDiagram, etc.).

    Return ONLY the Mermaid code, no markdown fences or explanations.
    """
}

# Create default prompt template manager
default_prompt_manager = PromptTemplate(default_templates=DEFAULT_TEMPLATES)
