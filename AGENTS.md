# NewPageMergeMDL project direction

The user-defined objective is one integrated model compiler based on PulseModel,
combining useful features from StudioMDL-CE, NekoMDL, StudioMDL 2013 and StudioMDL++.
Use FEATURE_MATRIX.md as the integration checklist. Prioritize a missing advertised
feature or concrete model compatibility defect over new infrastructure tasks.
Tests, performance work and publishing support these features; they are not the
primary completion criteria. Do not describe bounded examples as complete parity.

After implementation, fixes or new validation, proactively reconcile README.md,
README.en.md, COMPATIBILITY.md and the feature matrix. Keep historical results
clearly historical and distinguish intentional differences from bugs. Increment
the project version for compiler changes and refresh automation/compatibility.patch.

The two user-supplied 2012/2013 packages contain the same executable with different
game dependency configurations. Treat them as one feature source and preserve
separate runtime/dependency evidence. Do not reopen previously explained format
limits unless new evidence changes the implementation conclusion.

CE/StudioMDL++/Neko updates are supplied by the user; automatically integrate
PulseModel source updates. Reference binaries and user model assets stay outside
source commits and release packages.

Use C:/Users/Kud/Desktop/gmod/playermodel_f_compile2_hair.qc (Plum) for
production validation, including its supplied material assets. Do not use Claudia
for new validation. Keep original inputs unchanged and output paths isolated.
