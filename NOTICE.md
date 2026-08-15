# Notes on external assets

This repository contains deployment/configuration code and the user-supplied Goon Machine workflow JSON. It does not redistribute model weights.
Model files are downloaded at instance startup from their original hosting services and remain subject to the licenses/terms of those model authors and hosts.

The original workflow is preserved unchanged as `workflows/GoonMachine_original_v08.json`. Generated SAFE/FULL variants only adjust paths, source-selection and selected optional nodes for Linux/Vast/RTX 5090 deployment.
