# FreeCAD_for_Eitech
Helper macros for documenting Eitech metal construction set models with FreeCAD. 

This repository facilitates the development and documentation of models made of metal construction sets (in this case Eitech) using FreeCAD. Might end up in an Eitech Workbench.

The basic idea is to use the new Assembly workbench.

The following problems have been identified:

- Performence of multi-part assemblies
 - Adding new parts takes longer and longer the more parts are added. Even just 100 rigidly connected parts can be a problem.
 - Mitigation: Split into sub-assemblies (one per file) and insert them in master assemblies as rigid or use simple placement instead of joints.
- Severe problems wit closed loop kinematics. Even a simple four-link mechanism is hardly manageable.

Helper scripts

The scripts have been developed using with AI support.

- `nuts and bolts.py` Streamlines the insertion of nuts and bolts into a model.
- `ropes.py` create wire parts representing ropes based on a set of pulleys, winch and anchor points. Updates upon request (refresh button) when the assembly is moved.
- `edit_constraints.py` Select a component and get a list of mating parts (connected by joints) along with highlighting in the 3D window. Provides buttons for deleting and editing the joints.
- `track.py` creates parts representing the rubber-made caterpillar tracks of the Eitech system. Just specify the wheels/pulleys around which the track is wrapped.
- `bom.py` creates a bill of materials summing up over the whole assembly hierarchy.
