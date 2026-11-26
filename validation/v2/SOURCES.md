# Test set v2 sources

Test set v2 is synthetic. Every tag, value, device and sentence in it was written for this project by
`tools/make_v2_sets.py` and `tools/v2_templates.py`. No text from a real project, client or job folder is
used. The public documents below shaped what the packages contain: which sequences, which points, which
columns and which alarm and interlock requirements. Nothing was copied word for word. Each source was
retrieved on 2026-11-26.

## Used

| source | URL | license or terms | how it is used |
|---|---|---|---|
| UFGS 23 09 00 Instrumentation and Control for HVAC (USACE / NAVFAC / AFCEC, August 2024, Change 1 08/25) | https://www.wbdg.org/FFC/DOD/UFGS/UFGS%2023%2009%2000.pdf | Prepared by US federal agencies. A work of the US Government is not subject to copyright in the US (17 U.S.C. 105), and the PDF carries no copyright notice. | Points schedule columns (paragraph 3.3.10: point name, description, DDC hardware identifier, settings, range, I/O type, alarm information), the definition of alarm generation (paragraph 1.4.1) and the rule that the DDC hardware identifier is the same across all drawings, all paraphrased in the spec PART 1 lines and the points list columns. |
| UFGS 23 09 23.02 BACnet Direct Digital Control for HVAC and Other Building Control Systems (USACE / NAVFAC / AFCEC, August 2024) | https://www.wbdg.org/FFC/DOD/UFGS/UFGS%2023%2009%2023.02.pdf | US Government work, as above. | Binary and analog input and output object types, and the expectation that every point on the points schedule is provided as indicated. |
| UFGS 25 10 10 Utility Monitoring and Control System Front End and Integration (USACE / NAVFAC / AFCEC, February 2019, Change 2 08/25) | https://www.wbdg.org/FFC/DOD/UFGS/UFGS%2025%2010%2010.pdf | US Government work, as above. | Division 25 context for alarm generation and handling. No text used. |
| VA Section 23 09 23 Direct-Digital Control System for HVAC (Department of Veterans Affairs, 03-01-23) | https://www.wbdg.org/FFC/VA/VAASC/VA%2023%2009%2023.pdf | US Government work, as above. | A second public Division 23 controls specification, read for the safeties a controls spec requires (smoke detector and freeze-stat shutdown hardwired, manual reset, emergency stops). No text used. |
| Modelica Buildings Library, package `Buildings.Controls.OBC.ASHRAE.G36` (Lawrence Berkeley National Laboratory and contributors), commit `79f33d6612c84b4caf63992af72f21f05c67d931` | https://github.com/lbl-srg/modelica-buildings/tree/79f33d6612c84b4caf63992af72f21f05c67d931/Buildings/Controls/OBC/ASHRAE/G36 | BSD 3-clause style license, https://github.com/lbl-srg/modelica-buildings/blob/master/Buildings/legal.html (notice below). | The sequence logic of the multizone and single zone VAV air handling units, VAV reheat terminals, fan coil units and the chilled water plant (operating modes, supply air temperature and static pressure trim and respond reset, freeze protection stages, economizer lockouts, terminal unit alarms), as documented in its model files `AHUs/MultiZone/VAV/SetPoints/SupplyTemperature.mo`, `SupplyFan.mo`, `FreezeProtection.mo`, `ReliefDamper.mo`, `PlantRequests.mo`, `AHUs/MultiZone/VAV/Economizers/Controller.mo`, `AHUs/MultiZone/VAV/Controller.mo`, `AHUs/SingleZone/VAV/Controller.mo`, `TerminalUnits/Reheat/Controller.mo`, `FanCoilUnits/Controller.mo`, `Plants/Chillers/Controller.mo` and `Generic/TimeSuppression.mo`. Paraphrased into new sentences; no code or documentation text is redistributed. |

Modelica Buildings Library notice, reproduced as its license asks:

> Modelica Buildings Library. Copyright (c) 1998-2026 Modelica Association, International Building
> Performance Simulation Association (IBPSA), The Regents of the University of California, through Lawrence
> Berkeley National Laboratory (subject to receipt of any required approvals from the U.S. Dept. of Energy)
> and contributors. All rights reserved. Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the copyright notice, the list of conditions and the disclaimer
> are retained, and that the names of the copyright holders and contributors are not used to endorse or
> promote derived products without specific prior written permission. THIS SOFTWARE IS PROVIDED BY THE
> COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES ARE DISCLAIMED.

## Skipped

| source | why |
|---|---|
| ASHRAE Guideline 36 (High-Performance Sequences of Operation for HVAC Systems) | ASHRAE copyright with no reuse grant. Its text is not used. The G36 logic in this set comes only from the BSD licensed Modelica Buildings Library documentation above, which implements it. |
| A public sample points list or submittal excerpt with explicit reuse terms | None was found. The points lists and drawing device lists are synthetic, laid out with the UFGS 23 09 00 paragraph 3.3.10 columns. |
| USACE HVAC control systems guide, https://www.wbdg.org/files/pdfs/usace_hvac_controlsystems.pdf | The server returned a 501 byte stub instead of the PDF, so it could not be read. |
| UFC 3-410-02 Direct Digital Control for HVAC (2018 edition, archived as cancelled on WBDG) | Not needed once UFGS 23 09 00 and 23 09 23.02 were in hand; not used. |
| State master specifications found by search (for example a state agency Division 23 DDC section) | Reuse terms not stated; not used. |

## Limitation

Every v2 package is built from public and synthetic material in a fixed layout (`SECTION:` lines,
numbered paragraphs, CSV points and drawing lists). Real exported submittals are longer, messier and laid
out differently, so scores on this set do not carry over to real submittals without a test on real ones.
