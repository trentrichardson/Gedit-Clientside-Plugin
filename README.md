Gedit Clientside Plugin
=======================

Copyright 2010 Trent Richardson

This file is part of Gedit Clientside Plugin.

Gedit Clientside Plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

Gedit Clientside Plugin is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Gedit Clientside Plugin. If not, see <http://www.gnu.org/licenses/>.

ABOUT
-----
This Gedit plugin provides common tools for developing with clientside languages 
javascript and css. Tools for javascript include:

- [JS-Beautifier](http://jsbeautifier.org/) to format and "Unminify"
- [JSMin](http://www.crockford.com/javascript/jsmin.html) to minify
- [JSLint](http://www.jslint.com/) to look for syntax issues

Tools for CSS:

- [CSSTidy](http://csstidy.sourceforge.net/) to format and clean
- CSS Minification


PREREQUISITES
-------------
NodeJS: <http://nodejs.org/>

For Ubuntu use: 

	sudo apt-get install nodejs

For other linux distrobutions this may be a click away in your package manager. 
The plugin uses nodejs to execute serverside javascript (jslint and jsbeautify)


INSTALL
-------

- Copy the clientside directory and clientside.gedit-plugin file into your gedit plugins directory.
- Start or restart gedit
- Open the Preferences, and navigate to Plugins, check to enable Clientside plugin

CONFIGURE
---------
Once you've installed the plugin you can configure it to your needs through the Gedit Plugins Tab and click Configure, or through the Tools->Clientside menu.

Since this plugin uses NodeJS it needs to know how to call it.  Inside the configuration window there is a field for the command to call from a terminal.  
If you've installed nodejs manually, it is likely accessible through the command using "node".  However, though Ubuntu's package manager you will need to 
use "nodejs".  And, on some occasions, you may have to actually point to the binary file location (Mac might be /usr/local/bin/node).  If you need help you 
can try running in a terminal (unix or linux) the which tool: "which nodejs" or "which node".  This should print out a file path to the binary.

When formmatting your code the clientside plugin tries to pull some settings from gedit, like whether to use tab characters or spaces, and how many spaces are 
in a tab. The other setting is if brackets "{" should be placed on their own line.  Checking the box will result in:

	if(str == "hello world")
	{
		// ...
	}

Unchecking the box will look like this:

	if(str == "hello world"){
		// ...
	}

USE
---

- With your js or css file the active document go to Tools -> Clientside -> desired tool
- When you minify, format, or gzip a file you will be asked if you want to replace the current file contents
- With JSLint the bottom pane will have a new tab with any issues found
