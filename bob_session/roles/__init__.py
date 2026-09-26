"""Person B's cognitive layer: role prompts, context assembly, cascade, dispatch.

Modules:
  context.py        bundles + the sufficiency gate + runtime placeholder filling (B4)
  envelope.py       the claim envelope: the only language the models may speak (B3)
  cascade.py        the verification-gated cascade (B6)
  dispatch.py       subagent dispatch rules: one writer per file, clean contexts (B6)
  kernel_client.py  transport for the four MCP tools (Person A owns the server)
  errors.py         the layer's error taxonomy: every failure mode has a name
  testing.py        test doubles and unit builders (not the kernel)
"""
