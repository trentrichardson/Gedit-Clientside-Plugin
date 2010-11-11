# Copyright 2010 Trent Richardson
#
# This file is part of Gedit Clientside Plugin.
#
# Gedit Clientside Plugin is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# Gedit Clientside Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gedit Clientside Plugin. If not, see <http://www.gnu.org/licenses/>.

from StringIO import StringIO
from jsmin import JavascriptMinify
from csstidy import CSSTidy

import gtk
import gedit
import os
import re
import gzip
import subprocess

ui_str = """
<ui>
	<menubar name="MenuBar">
		<menu name="ToolsMenu" action="Tools">
			<placeholder name="ToolsOps_2">
				<menu name="ClientsideMenu" action="ClientsideMenuAction">
					<menuitem name="ClientsideJSFormat" action="ClientsideJSFormat"/>
					<menuitem name="ClientsideJSMinify" action="ClientsideJSMinify"/>
					<menuitem name="ClientsideJSLint" action="ClientsideJSLint"/>
					<separator />
					<menuitem name="ClientsideCSSFormat" action="ClientsideCSSFormat"/>
					<menuitem name="ClientsideCSSMinify" action="ClientsideCSSMinify"/>
					<separator />
					<menuitem name="ClientsideGzip" action="ClientsideGzip"/>
				</menu>
			</placeholder>
		</menu>
	</menubar>
</ui>
"""

class ClientsideWindowHelper:
	def __init__(self, plugin, window):
		self._window = window
		self._plugin = plugin
		self.tab = None
		self.pane = None
		
		self.clipboard = gtk.Clipboard(gtk.gdk.display_get_default(), "CLIPBOARD")
		
		self.plugin_dir = os.path.split(__file__)[0]
		self.config_store = os.path.join(self.plugin_dir, "defaults.pkl")
		
		self._settings = {
							'use_clipboard': True,
							'nodejs': 'node',
							'indent_size': '1',
							'indent_char': '\t',
							'braces_on_own_line': 'false',
							'preserve_newlines': 'true',
							'keep_array_indentation': 'true',
							'space_after_anon_function': 'true',
							'decompress': 'true',
							'csstidy_minify': 'highest_compression',
							'csstidy_beautify': 'low_compression',
						}
		
		self._insert_menu()
		
		self._find_nodejs_binary(['nodejs','node'])

	def deactivate(self):
		self._remove_menu()
		
		self._window = None
		self._plugin = None
		self._action_group = None
		self.clipboard = None

	def _insert_menu(self):
		manager = self._window.get_ui_manager()
		
		# Create a new action group
		self._action_group = gtk.ActionGroup("ClientsidePluginActions")
		self._action_group.add_actions([
			("ClientsideMenuAction", None, _("Clientside"), None, _("Clientside Tools : For JS and CSS"), None),
			("ClientsideJSFormat", None, _("Format JS"), None, _("Format JS"), self.on_format_js_activate),
			("ClientsideJSMinify", None, _("Minify JS"), "<Ctrl>U", _("Minify JS"), self.on_minifier_js_activate),
			("ClientsideJSLint", None, _("JSLint"), None, _("JSLint"), self.on_lint_js_activate),
			("ClientsideCSSFormat", None, _("Format CSS"), None, _("Format and Clean CSS"), self.on_format_css_activate),
			("ClientsideCSSMinify", None, _("Minify CSS"), "<Ctrl><Shift>U", _("Minify CSS"), self.on_minifier_css_activate),
			("ClientsideGzip", None, _("Gzip Current File"), "<Ctrl><Alt>U", _("Gzip Current File"), self.on_minifier_gzip_activate)
		])
		
		manager.insert_action_group(self._action_group, -1)
		self._ui_id = manager.add_ui_from_string(ui_str)

	def _remove_menu(self):        
		manager = self._window.get_ui_manager()
		manager.remove_ui(self._ui_id)
		manager.remove_action_group(self._action_group)
		manager.ensure_update()

	def update_ui(self):
		self._action_group.set_sensitive(self._window.get_active_document() != None)
		if self.pane:
			if self.tab != self._window.get_active_tab():
				self.lines = []
				self.errorlines.clear()
				self._window.get_bottom_panel().remove_item(self.pane)
				self.pane = None
		return
	
	#================================================================================
	# Some utility functions
	#================================================================================
	
	# -------------------------------------------------------------------------------
	def _get_cmd_output(self,cmd):
		#-----------------------
		#fin,fout = os.popen4(cmd)
		#result = fout.read()
		#fin.close()
		#fout.close()
		
		#-----------------------
		#result = os.system(cmd)
		
		#-----------------------
		p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
		#result = p.stdout.read()
		#p.stdout.close()
		result = p.communicate()[0]
		p.wait()
		
		return result
	
	# -------------------------------------------------------------------------------
	def _find_nodejs_binary(self, choices):
		
		for v in choices:
			tmp = self._get_cmd_output("which "+ v)
			if tmp != "":
				self._settings['nodejs'] = v
				return
			
		print "Unable to locate NodeJS. Is it installed?"
	
	# -------------------------------------------------------------------------------
	def _import_gedit_preferences(self):
		view = self._window.get_active_view()
		
		try:
			indent_with_spaces = view.get_insert_spaces_instead_of_tabs() #true means use spaces
			
			if indent_with_spaces:
				indent_size = view.get_tab_width()
				
				self._settings['indent_size'] = str(indent_size)
				self._settings['indent_char'] = ' '
			else:
				self._settings['indent_size'] = '1'
				self._settings['indent_char'] = '\t'
				
		except err:
			print "Unable in import settings to Clientside plugin"
		
		return
	
	
	#================================================================================
	# handle bottom tab population and click events
	#================================================================================
	
	# -------------------------------------------------------------------------------
	def row_clicked(self, treeview, path, view_column, doc):
		lineno, charno = self.lines[path[0]]
		view = self._window.get_active_view()
		
		doc.goto_line(lineno)
		view.scroll_to_cursor()
		view.grab_focus()
		
	
	# -------------------------------------------------------------------------------
	def populate_bottom_tab(self, errorlist=[]):
		self.errorlines.clear()
		self.lines = []
		
		# errorlist = [ [line_num, char_position, "error text"],... ] 
		for e in errorlist:
			self.errorlines.append([int(e[0]), int(e[1]), e[2]])
			self.lines.append([int(e[0]-1), int(e[1]-1)])
        
		self._window.get_bottom_panel().set_property("visible", True)
		self._window.get_bottom_panel().activate_item(self.pane)
	
	
	# -------------------------------------------------------------------------------
	def create_bottom_tab(self):
		doc = self._window.get_active_document()
		self.tab = self._window.get_active_tab()
		if not doc:
			return
		
		if not self.pane:
			self.errorlines = gtk.ListStore(int,int,str)
			self.pane = gtk.ScrolledWindow()
			treeview = gtk.TreeView(model=self.errorlines)
			
			lineno = gtk.TreeViewColumn('Line')
			charno = gtk.TreeViewColumn('Char')
			message = gtk.TreeViewColumn('Message')
			
			treeview.append_column(lineno)
			treeview.append_column(charno)
			treeview.append_column(message)
			
			cell1 = gtk.CellRendererText()
			cell2 = gtk.CellRendererText()
			cell3 = gtk.CellRendererText()
			
			lineno.pack_start(cell1,True)
			charno.pack_start(cell2, True)
			message.pack_start(cell3, True)
			
			lineno.set_attributes(cell1, text=0)
			charno.set_attributes(cell2, text=1)
			message.set_attributes(cell3, text=2)
			
			bottom = self._window.get_bottom_panel()
			image = gtk.Image()
			image.set_from_icon_name('gtk-dialog-warning', gtk.ICON_SIZE_MENU)
			self.pane.add(treeview)
			bottom.add_item(self.pane, 'Clientside Issues', image)
			treeview.connect("row-activated", self.row_clicked, doc)
			self.pane.show_all()
			
		
	#================================================================================
	# Action functions
	#================================================================================
	
	# -------------------------------------------------------------------------------
	# js lint button click
	def on_lint_js_activate(self, action):
		doc = self._window.get_active_document()
		self.tab = self._window.get_active_tab()
		if not doc:
			return
		
		jslint_path = os.path.join(self.plugin_dir, "jslint_node")
		tmpfile_path = os.path.join(self.plugin_dir, "tmp_jslint.js")
		tmpcode_path = os.path.join(self.plugin_dir, "tmp_jslint_code.js")
		
		tmpfile = open(tmpfile_path,"w")
		tmpfile.writelines("var sys = require('sys');")
		tmpfile.writelines("var fs = require('fs');")
		tmpfile.writelines("var JSLINT = require('" + jslint_path + "').JSLINT;")
		tmpfile.writelines("var body = fs.readFileSync('" + tmpcode_path + "');")
		tmpfile.write('''
			body = body.toString("utf8");
			var result = JSLINT(body, {browser: true, forin: true});
			var errors = [];
			if(JSLINT.errors){
				for(var i=0; i<JSLINT.errors.length; i++){
					if(JSLINT.errors[i]){
						process.stdout.write(JSLINT.errors[i].line +','+ JSLINT.errors[i].character +',"'+ JSLINT.errors[i].reason.toString().replace('"','\"') +'"\\n');
						errors.push('{"reason":"' + JSLINT.errors[i].reason + '", "line":' + JSLINT.errors[i].line + ', "character":' + JSLINT.errors[i].character + '}');
					}
				}
			}
			process.exit(0);
		''')
		tmpfile.close()
		
		# store in tmp file
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter())
		tmpcode = open(tmpcode_path,"w")
		tmpcode.write(doctxt)
		tmpcode.close()
		
		# run validation
		result = self._get_cmd_output(self._settings['nodejs'] +' ' + tmpfile_path)
		
		#clean up
		os.remove(tmpcode_path)
		os.remove(tmpfile_path)
		
		# we need to format it for our populate routine
		jslint_results = result.splitlines()
		elist = []
		for e in jslint_results:
			tmpparts = e.split(',')#re.split(r'\s*("[^"]*"|.*?)\s*,',e)
			if len(tmpparts) > 0:
				elist.append([int(tmpparts[0]), int(tmpparts[1]), tmpparts[2]])
		
		self.create_bottom_tab()
		self.populate_bottom_tab(elist)
		
	# -------------------------------------------------------------------------------	
	# js beautify button click
	def on_format_js_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
		
		self._import_gedit_preferences()
		
		jsbeautify_path = os.path.join(self.plugin_dir, "jsbeautify/beautify")
		tmpfile_path = os.path.join(self.plugin_dir, "tmp_jsbeautify.js")
		tmpcode_path = os.path.join(self.plugin_dir, "tmp_jsbeautify_code.js")
		
		tmpfile = open(tmpfile_path,"w")
		tmpfile.writelines("var sys = require('sys');")
		tmpfile.writelines("var fs = require('fs');")
		tmpfile.writelines("var js_beautify = require('" + jsbeautify_path + "').js_beautify;")
		tmpfile.writelines("var body = fs.readFileSync('" + tmpcode_path + "');")
		tmpfile.writelines("var options = { indent_size: "+ self._settings['indent_size'] +", indent_char: '"+ self._settings['indent_char'] +"', preserve_newlines: "+ self._settings['preserve_newlines'] +", space_after_anon_function: "+ self._settings['space_after_anon_function'] +", keep_array_indentation: "+ self._settings['keep_array_indentation'] +", braces_on_own_line: "+ self._settings['braces_on_own_line'] +" };")
		tmpfile.write('''
			body = body.toString("utf8");
			var result = js_beautify(body, options);
			process.stdout.write(result);
			process.exit(0);
		''')
		tmpfile.close()
		
		# store in tmp file
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter())
		tmpcode = open(tmpcode_path,"w")
		tmpcode.write(doctxt)
		tmpcode.close()
		
		# run command
		result = self._get_cmd_output(self._settings['nodejs'] +' ' + tmpfile_path)
		
		#clean up
		os.remove(tmpcode_path)
		os.remove(tmpfile_path)
		
		#print result
		self.handle_new_output("Formatted JS Copied to Clipboard.", result)
		
	
	# -------------------------------------------------------------------------------	
	# js minify button click
	def on_minifier_js_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
			
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter())
		
		ins = StringIO(doctxt)
		outs = StringIO()
		
		JavascriptMinify().minify(ins, outs)
		
		min_js = outs.getvalue()
		
		if len(min_js) > 0 and min_js[0] == '\n':
			min_js = min_js[1:]
		
		min_js = re.sub(r'(\n|\r)+','', min_js)
		
		self.handle_new_output("Minified JS Copied to CLipboard", min_js)
		

	# -------------------------------------------------------------------------------
	# css format button click
	def on_format_css_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
		
		self._import_gedit_preferences()
		
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter())
		
		tidy = CSSTidy()
		tidy.setSetting('template', self._settings['csstidy_beautify'])
		tidy.setSetting('indent', '\t')
		tidy.parse(doctxt)
		formatted_css = tidy.Output('string')
		
		if self._settings['indent_char'] == ' ':
			formatted_css = re.sub(r'\t', ' '* int(self._settings['indent_size']), formatted_css)
        
		self.handle_new_output("Formatted CSS Copied to Clipboard.", formatted_css)
		
	
	# -------------------------------------------------------------------------------	
	# css minify button click
	def on_minifier_css_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
			
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter())
		formatted_css = self.get_minified_css_str(doctxt)
		
		# our function seems better than csstidy :-/
		#tidy = CSSTidy()
		#tidy.setSetting('template', self._settings['csstidy_minify'])
		#tidy.parse(doctxt)
		#formatted_css = tidy.Output('string')
		
		self.handle_new_output("Minified CSS Copied to Clipboard.", formatted_css)
		
	
	# -------------------------------------------------------------------------------
	# gzip button click
	def on_minifier_gzip_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
		
		docuri = doc.get_uri_for_display()
		docfilename = doc.get_short_name_for_display()
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter())
		docfilenamegz = docfilename + '.gz'
		
		dialog = gtk.FileChooserDialog(title=None,action=gtk.FILE_CHOOSER_ACTION_SAVE,buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK))
		dialog.set_do_overwrite_confirmation(True)
		dialog.set_current_folder(os.path.split(docuri)[0])
		dialog.set_current_name(docfilenamegz)
		dialog.set_default_response(gtk.RESPONSE_OK)
       
		response = dialog.run()
		
		if response == gtk.RESPONSE_OK:
			newgzuri = dialog.get_filename()
			
			f = gzip.open(newgzuri, 'wb')
			f.write(doctxt)
			f.close()
			f = None
		
		dialog.destroy()

	#================================================================================
	# Helper Functions
	#================================================================================
	
	# -------------------------------------------------------------------------------
	# the guts of how to minify css: 
	# credit: http://stackoverflow.com/questions/222581/python-script-for-minifying-css
	def get_minified_css_str(self, css):
		
		# remove comments - this will break a lot of hacks :-P
		css = re.sub( r'\s*/\*\s*\*/', "$$HACK1$$", css ) # preserve IE<6 comment hack
		css = re.sub( r'/\*[\s\S]*?\*/', "", css )
		css = css.replace( "$$HACK1$$", '/**/' ) # preserve IE<6 comment hack
		
		# url() doesn't need quotes
		css = re.sub( r'url\((["\'])([^)]*)\1\)', r'url(\2)', css )
		
		# spaces may be safely collapsed as generated content will collapse them anyway
		css = re.sub( r'\s+', ' ', css )
		
		# shorten collapsable colors: #aabbcc to #abc
		css = re.sub( r'#([0-9a-f])\1([0-9a-f])\2([0-9a-f])\3(\s|;)', r'#\1\2\3\4', css )
		
		# fragment values can loose zeros
		css = re.sub( r':\s*0(\.\d+([cm]m|e[mx]|in|p[ctx]))\s*;', r':\1;', css )
		
		min_css = ""
		
		for rule in re.findall( r'([^{]+){([^}]*)}', css ):
		
			# we don't need spaces around operators
			selectors = [re.sub( r'(?<=[\[\(>+=])\s+|\s+(?=[=~^$*|>+\]\)])', r'', selector.strip() ) for selector in rule[0].split( ',' )]
			
			# order is important, but we still want to discard repetitions
			properties = {}
			porder = []
			for prop in re.findall( '(.*?):(.*?)(;|$)', rule[1] ):
				key = prop[0].strip().lower()
				if key not in porder:
					porder.append( key )
				properties[ key ] = prop[1].strip()
			
			# output rule if it contains any declarations
			if properties:
				min_css = min_css + "%s{%s}" % ( ','.join( selectors ), ''.join(['%s:%s;' % (key, properties[key]) for key in porder])[:-1] )
		
		return min_css
		
	
	# -------------------------------------------------------------------------------
	# ask the user what to do with the output
	def handle_new_output(self, remark, contents):
		view = self._window.get_active_view()
		remark = remark +"\n\nDo you want to replace it in the document?"
		
		#save to clipboard
		self.clipboard.set_text(contents)
		
		# do we want to overwrite current document?
		md = gtk.MessageDialog(type=gtk.MESSAGE_QUESTION, buttons=gtk.BUTTONS_YES_NO, flags=gtk.DIALOG_MODAL, message_format=remark)
		response = md.run()
		md.destroy()
		
		if response == gtk.RESPONSE_YES:
			
			# out with the old
			view.select_all()
			#view.delete_selection()
			
			# in with the new
			view.paste_clipboard()
	

#================================================================================
# Clientside Plugin Class
#================================================================================
class ClientsidePlugin(gedit.Plugin):
	def __init__(self):
		gedit.Plugin.__init__(self)
		self._instances = {}
	
	def activate(self, window):
		self._instances[window] =ClientsideWindowHelper(self, window)
	
	def deactivate(self, window):
		self._instances[window].deactivate()
		del self._instances[window]
	
	def update_ui(self, window):
		self._instances[window].update_ui()

