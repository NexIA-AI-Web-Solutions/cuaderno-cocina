

import os
from unittest.mock import MagicMock
from cookbook.helper.template_helper import render_instructions

def test_markdown_renderer():
    # Setup paths
    base_dir = os.path.dirname(__file__)
    test_data_dir = os.path.join(base_dir, 'test_data')
    base_file = os.path.join(test_data_dir, 'test_markdown_base')
    rendered_file = os.path.join(test_data_dir, 'test_markdown_rendered')

    # Read base markdown
    with open(base_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()

    # Mock Ingredient
    mock_ingredient = MagicMock()
    mock_ingredient.amount = 1.5
    mock_ingredient.no_amount = False
    mock_ingredient.note = "fresh"
    
    # Mock Food
    mock_food = MagicMock()
    mock_food.plural_name = "apples"
    mock_food.__str__.return_value = "apple"
    mock_ingredient.food = mock_food
    
    # Mock Unit
    mock_unit = MagicMock()
    mock_unit.plural_name = "kg"
    mock_unit.__str__.return_value = "kg"
    mock_ingredient.unit = mock_unit

    # Mock Step
    mock_step = MagicMock()
    mock_step.instruction = markdown_content
    mock_step.ingredients.all.return_value = [mock_ingredient]

    # Run render_instructions
    result = render_instructions(mock_step)

    # Fixtures are reviewed source, never regenerated from the implementation.
    assert os.path.isfile(rendered_file) and os.path.getsize(rendered_file) > 0

    # Read rendered markdown
    with open(rendered_file, 'r', encoding='utf-8') as f:
        expected_content = f.read()
    print(result)
    # Compare
    # The source fixture has a conventional final newline; renderer HTML does
    # not. Compare every byte of content plus that explicit file terminator.
    assert result + '\n' == expected_content
