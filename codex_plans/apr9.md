Make Imported Shoe Data Visible And Trustworthy In personalization-mvp
Summary
Keep main unchanged as the legacy production surface.
In personalization-mvp, make the product explicit about what it knows about the user by separating:
training history we have,
shoes we detected,
signals we are missing.
Make CSV-imported shoe names appear in the main shoe inventory even when they do not match the catalog.
Treat imported shoe names as inferred owned shoes for rotation and recommendation logic, but keep unmapped names honest and read-only.
Key Changes
Reframe the personalization page around a clear “Your data” model.
Replace the current profile panel emphasis with three visible summaries:
Training history
Shoes we detected
What’s missing
Rename the “Owned shoes” section to Your shoes.
Add copy above it: “Includes shoes you added manually and shoes we detected from imported activity history.”
Change the table rows so each shoe shows:
source (manual, manual + imported activity, imported activity)
catalog status (matched, unmapped)
display name
current mileage
retirement/health status when known
recent use count
Imported-but-unmapped shoes must render with the user’s raw imported name exactly as seen in CSV.
Do not force a best-guess catalog match.
Show them as unmapped and still include them in the visible inventory.
Improve first-run data clarity in the profile area using existing profile + rotation data:
total imported runs
detected shoe count
mapped shoe count
unmapped shoe count
missing-signal warnings
Update import success messaging so it tells the user what was found, not just how many activities were imported.
Example shape: “Imported 42 runs. Detected 3 shoe names, 1 matched to the catalog, 2 still unmapped.”
Backend And Interface Changes
Do not add a new persistence table for this pass.
Derive inferred shoes on the fly from ActivityFeature.gear_ref and merge them into the rotation summary.
Extend build_rotation_summary() to return a merged inventory:
manual OwnedShoe rows
inferred imported rows for unmatched gear_ref values
merged manual rows when imported gear names match an existing manual shoe identifier
Use conservative auto-mapping only:
exact normalized match against catalog identifiers such as display_name, brand + shoe_name, or shoe_name
if there is no exact normalized match, leave the shoe unmapped
Add stable synthetic IDs for inferred imported rows in API responses, for example imported:<normalized-gear-ref>.
These rows are display-only in this pass and are not editable through PATCH /api/rotation/shoes/{shoe_id}.
Extend OwnedShoeResponse with:
source_kind: "manual" | "manual_with_import" | "imported"
mapping_status: "catalog_matched" | "unmapped"
raw_import_name: string | null
activity_count: int
recent_uses_30d: int
Extend RotationResponse with a summary object containing:
manual_count
imported_count
mapped_count
unmapped_count
Ensure empty profiles include coverage.missing_signals, so the UI can always explain what data is absent.
Update recommendation logic to use the merged rotation summary as the shoe inventory source.
Imported mapped shoes can contribute catalog anchors and rotation overlap logic.
Imported unmapped shoes count toward visible inventory and rotation breadth, but cannot be used as similarity anchors.
Keep unmapped imported shoes read-only for this pass.
No manual mapping workflow is added in this iteration.
Test Plan
Add a rotation-summary test where imported CSV activities contain a shoe name with no catalog match.
Assert the shoe appears in GET /api/rotation as source_kind=imported and mapping_status=unmapped.
Add a merge test where imported gear_ref matches a manual owned shoe.
Assert only one row is returned and its source becomes manual_with_import.
Add a conservative auto-mapping test:
exact normalized names map
loose nicknames do not map
Add an import endpoint test asserting the import response summary includes detected shoe counts and mapped/unmapped counts.
Add a profile test asserting coverage.missing_signals exists even when the user has zero runs.
Add a UI smoke test for the personalization page contract:
with only CSV-imported gear, the “Your shoes” table is non-empty and contains imported rows with raw names.
Assumptions And Defaults
Imported shoe rows are merged into the main shoe table, not shown in a separate section.
Unmapped imported names stay as raw user-provided names and are not hidden.
Auto-matching is conservative and exact-normalized only; no fuzzy matching in this pass.
Inferred imported rows are read-only for now; manual mapping/editing is a later feature.
No DB migration is required for this iteration; the new behavior is derived from existing gear_ref activity data.
