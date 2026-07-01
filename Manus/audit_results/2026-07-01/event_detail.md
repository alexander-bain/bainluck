Starting the Event Detail Deep Audit of bainluck.com. I'll browse the site, select 6 events across different sports and statuses, then perform a comprehensive quality audit of each event detail page.

I've completed the desktop audit of all 6 events. I found a critical issue: the "upcoming" event (14970056) returned "Event not found", and the event I selected as a future game (14626093, Jul 7) is incorrectly marked as "Final" with a 0-0 score. Now proceeding to mobile viewport testing.

I have completed the deep audit of the 6 event detail pages on bainluck.com as requested. 

The audit covered 2 LIVE events, 3 FINAL events, and 1 UPCOMING event across Soccer, Tennis, and Baseball.

**Key Findings:**
- The overall health score is **31/100**, heavily impacted by a few critical data integrity and rendering issues.
- **Critical Issue:** A future game (Jul 7) was incorrectly marked as "Final" with a 0-0 score and fabricated chart data.
- **Critical Issue:** The Score Differential chart failed to render (collapsed) on multiple MLB event pages.
- **Critical Issue:** One of the selected upcoming events returned an "Event not found" error despite being linked from the main feed.
- **Warnings:** Player props were frequently missing, related futures showed entity matching errors (e.g., England soccer linked to Women's T20 cricket), and resolved props lacked clarity on which side won.

On the positive side, the win probability charts are data-rich with multiple sources, inning markers on MLB charts provide excellent context, and cross-page consistency between the feed and detail pages is very strong.

I've attached the comprehensive audit report (`Event_Detail_Audit_Report.md`) following your exact format, along with a zip file containing all the requested desktop and mobile (375px) screenshots for each event.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/QMzwe9qZLZnczBZSMEoRjN/sandbox/s8kFJrPfvndPn0VMYV6lKq_1782923941769_na1fn_L2hvbWUvdWJ1bnR1L0V2ZW50X0RldGFpbF9BdWRpdF9SZXBvcnQ.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvUU16d2U5cVpMWm5jekJaU01Fb1JqTi9zYW5kYm94L3M4a0ZKclBmdm5kUG4wVk1ZVjZsS3FfMTc4MjkyMzk0MTc2OV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDBWMlpXNTBYMFJsZEdGcGJGOUJkV1JwZEY5U1pYQnZjblEubWQiLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE4MzAyOTc2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=bHIZC~cjgv7VgKQ4uUvbyQKjcFNzjXth5dZA9newFY4AJnBnoIW~RbkjgokzlpZ2Gr0F9vqw3Mh-nbj5O4PWW4DuuW1phYyX~p7mABTUmwuL1MYE1~OFpIWkMZgPzxplPHCp3cp1OuUtC1Lv~VfZJJjod62J0~DrzOHJc1YjFy0e0fu1vXlS9oNxf0XZtpCcHl4VQhw2bRp2J6Np-UF1bL9BZMahwfCfBUiAEDYuTNxyG6aZ0QVfFGrlUxjWIGf-xZhS-UVzbcQjykNUgyxYTh4OcpFZgcmPT2Nc7WAskE9W58Ahs1xkbkiOilN1n~R-2bZMCAOKamLa3nIeo0Bqqw__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/QMzwe9qZLZnczBZSMEoRjN/sandbox/s8kFJrPfvndPn0VMYV6lKq_1782923941769_na1fn_L2hvbWUvdWJ1bnR1L2F1ZGl0X3NjcmVlbnNob3Rz.zip?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvUU16d2U5cVpMWm5jekJaU01Fb1JqTi9zYW5kYm94L3M4a0ZKclBmdm5kUG4wVk1ZVjZsS3FfMTc4MjkyMzk0MTc2OV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJGMVpHbDBYM05qY21WbGJuTm9iM1J6LnppcCIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTgzMDI5NzYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=XGBjCulET98T4LgXk9yC-06r5aG376Zm6OWrrdU4fdOOkvZZviHnlIKu8Z-fGDpAhNT1-ThY3yMcE5Uxj5eZ0Nz0TmAFq~TAICe4SemXjTMxzFuq0ZRRdpqZZ6nh~0BhYtVbY-9ZhQaZvbx7fc~UMFwIHEGRZdSIbIA9yHYBiJ5ZBe0GMexNlNx8bINgEhIcsaoCPIiGOXmEsuPads3O5TD8xfeCSvrU-LHEK9S1b-AHDhdsOjs1FPDE1FZW2L0lcs6ldA6aSMmzxCpp1mP4TzXPF4-~Dr8gAKQbF4SZbXxPIVS2Bb00~Yaz1pEO9ZVdbyPILb70NhxTgkkTtX9ZXQ__