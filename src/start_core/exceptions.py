"""
This module defines all of the internal exceptions that may be thrown by the
START framework.
"""
class STARTException(Exception):
    """
    Base class used by all START exceptions.
    """

class CLIException(STARTException):
    """
    Base class used by all checked exceptions that are thrown by the CLI.
    """

class BadBugZooManifest(STARTException):
    """
    The BugZoo manifest used by START has been corrupted and does not match
    the expected format.
    """
