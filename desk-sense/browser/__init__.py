"""Browser agent, engine side: turns a page's element table into one fast decision per step.

Runs in the supervisor process, never in the worker. The page is untrusted data: element names are
only ever offered as options to pick from, and typed values come from the plan, never from the page.
"""
