---
name: unit-converter
description: A simple unit conversion skill that converts between metric and imperial units. Supports length, weight, and temperature conversions.
---

# Unit Converter

A reliable unit conversion assistant that handles metric ↔ imperial conversions.

## Description

Convert between common units: kilometers/miles, kilograms/pounds, Celsius/Fahrenheit. Supports single and batch conversions with clear output formatting.

## Usage

1. Ask a conversion question: "Convert 5 km to miles"
2. Get the precise result with explanation

## Examples

- "Convert 100 km to miles"
- "What is 72°F in Celsius?"
- "How many pounds is 50 kg?"

## Capabilities

### Capability 1: Length Conversion

- Convert km ↔ miles, m ↔ feet, cm ↔ inches
- Input: number + source unit
- Output: converted value + target unit

### Capability 2: Weight Conversion

- Convert kg ↔ pounds, g ↔ ounces
- Input: number + source unit
- Output: converted value + target unit

### Capability 3: Temperature Conversion

- Convert °C ↔ °F, °C ↔ K
- Input: number + scale
- Output: converted value + target scale

## Triggers

- Keywords: "convert", "conversion", "km to miles", "kg to pounds", "celsius to fahrenheit"
- Pattern: number followed by unit name

## Output Format

```
{input_value} {input_unit} = {result_value} {output_unit}
```

## Edge Cases

- Negative temperatures handled correctly
- Zero input returns zero output
- Very large numbers use scientific notation
