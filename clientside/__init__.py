# Copyright 2011 Trent Richardson
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
from cssmin import CSSMin

from gi.repository import GObject, Gtk, Gdk, Gedit, PeasGtk
import os
import re
import gzip
import subprocess
import pickle

ui_str = """
<ui>
	<menubar name="MenuBar">
		<menu name="ToolsMenu" action="Tools">
			<placeholder name="ToolsOps_2">
				<menu name="ClientsideMenu" action="ClientsideMenuAction">
					<menuitem name="ClientsideJSFormat" action="ClientsideJSFormat"/>
					<menuitem name="ClientsideJSMinify" action="ClientsideJSMinify"/>
					<menuitem name="ClientsideJSBatchMinify" action="ClientsideJSBatchMinify"/>
					<menuitem name="ClientsideJSLint" action="ClientsideJSLint"/>
					<separator />
					<menuitem name="ClientsideCSSFormat" action="ClientsideCSSFormat"/>
					<menuitem name="ClientsideCSSMinify" action="ClientsideCSSMinify"/>
					<menuitem name="ClientsideCSSBatchMinify" action="ClientsideCSSBatchMinify"/>
					<menuitem name="ClientsideCSSLint" action="ClientsideCSSLint"/>
					<separator />
					<menuitem name="ClientsideGzip" action="ClientsideGzip"/>
					<separator />
					<menuitem name="ClientsideConfig" action="ClientsideConfig"/>
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
		
		atom = Gdk.atom_intern('CLIPBOARD', True)
		self.clipboard = Gtk.Clipboard.get(atom)
		
		self.plugin_dir = os.path.split(__file__)[0]
		self.config_store = os.path.join(self.plugin_dir, "defaults.pkl")
		self.config_fields = { 'nodejs': None, 'braces_on_own_line': None, 'replace_contents': None }
		
		self._settings = {
			'replace_contents': 2, # 0=clipboard, 1=replace, 2=ask what to do
			'nodejs': 'node',
			'indent_size': '1',
			'indent_char': '\t',
			'braces_on_own_line': 'false',
			'preserve_newlines': 'true',
			'keep_array_indentation': 'true',
			'space_after_anon_function': 'true',
			'decompress': 'true',
		}
		
		self._insert_menu()
		
		self._read_config_file()

	def deactivate(self):
		self._remove_menu()
		
		#remove bottom tab if it exists
		if self.pane:
			self._window.get_bottom_panel().remove_item(self.pane)
			self.pane = None
		
		self._window = None
		self._plugin = None
		self._action_group = None
		self.clipboard = None

	def _insert_menu(self):
		manager = self._window.get_ui_manager()
		
		# Create a new action group
		self._action_group = Gtk.ActionGroup("ClientsidePluginActions")
		self._action_group.add_actions([
			("ClientsideMenuAction", None, _("Clientside"), None, _("Clientside Tools : For JS and CSS"), None),
			("ClientsideJSFormat", None, _("Format JS"), None, _("Format JS"), self.on_format_js_activate),
			("ClientsideJSMinify", None, _("Minify JS"), "<Ctrl>U", _("Minify JS"), self.on_minifier_js_activate),
			("ClientsideJSBatchMinify", None, _("Batch Minify JS"), None, _("Batch Minify JS"), self.on_batch_minifier_js_activate),
			("ClientsideJSLint", None, _("JSLint"), "<ALT>U", _("JSLint"), self.on_lint_js_activate),
			("ClientsideCSSFormat", None, _("Format CSS"), None, _("Format and Clean CSS"), self.on_format_css_activate),
			("ClientsideCSSMinify", None, _("Minify CSS"), "<Ctrl><Shift>U", _("Minify CSS"), self.on_minifier_css_activate),
			("ClientsideCSSBatchMinify", None, _("Batch Minify CSS"), None, _("Batch Minify CSS"), self.on_batch_minifier_css_activate),
			("ClientsideCSSLint", None, _("CSSLint"), "<ALT><Shift>U", _("CSSLint"), self.on_lint_css_activate),
			("ClientsideGzip", None, _("Gzip Current File"), "<Ctrl><Alt>U", _("Gzip Current File"), self.on_minifier_gzip_activate),
			("ClientsideConfig", None, _("Configure Plugin"),None, _("Configure Plugin"),self.open_config_window),
		])
		
		manager.insert_action_group(self._action_group, -1)
		self._ui_id = manager.add_ui_from_string(ui_str)
		manager.ensure_update()

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
		
		p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
		#result = p.stdout.read()
		#p.stdout.close()
		result = p.communicate()[0]
		p.wait()
		
		return result
	
	
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
		lineno, charno = self.lines[path.get_indices()[0]]
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
			self.errorlines.append([int(e['line']), int(e['char']), e['text']])
			self.lines.append([int(e['line']-1), int(e['char']-1)])
        
		self._window.get_bottom_panel().set_property("visible", True)
		self._window.get_bottom_panel().activate_item(self.pane)
	
	
	# -------------------------------------------------------------------------------
	def create_bottom_tab(self):
		doc = self._window.get_active_document()
		self.tab = self._window.get_active_tab()
		if not doc:
			return
		
		if not self.pane:
			self.errorlines = Gtk.ListStore(int,int,str)
			self.pane = Gtk.ScrolledWindow()
			treeview = Gtk.TreeView(model=self.errorlines)
			
			lineno = Gtk.TreeViewColumn('Line', Gtk.CellRendererText(), text=0)
			charno = Gtk.TreeViewColumn('Char', Gtk.CellRendererText(), text=1)
			message = Gtk.TreeViewColumn('Message', Gtk.CellRendererText(), text=2)
			
			treeview.append_column(lineno)
			treeview.append_column(charno)
			treeview.append_column(message)
			
			"""
			lineno = Gtk.TreeViewColumn('Line')
			charno = Gtk.TreeViewColumn('Char')
			message = Gtk.TreeViewColumn('Message')
			
			treeview.append_column(lineno)
			treeview.append_column(charno)
			treeview.append_column(message)
			
			cell1 = Gtk.CellRendererText()
			cell2 = Gtk.CellRendererText()
			cell3 = Gtk.CellRendererText()
			
			lineno.pack_start(cell1,True)
			charno.pack_start(cell2, True)
			message.pack_start(cell3, True)
			
			lineno.set_attributes(cell1, text=0)
			charno.set_attributes(cell2, text=1)
			message.set_attributes(cell3, text=2)
			"""
			bottom = self._window.get_bottom_panel()
			image = Gtk.Image()
			image.set_from_icon_name('gtk-dialog-warning', Gtk.IconSize.MENU)
			self.pane.add(treeview)
			bottom.add_item(self.pane, 'ClientsideIssues', 'Clientside Issues', image)
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
			var out = '';
			
			if(JSLINT.errors){
				for(var i=0; i<JSLINT.errors.length; i++){
					if(JSLINT.errors[i]){
						out += JSLINT.errors[i].line +','+ JSLINT.errors[i].character +',"'+ JSLINT.errors[i].reason.toString().replace('"','\"') +'"\\n';
						errors.push('{"reason":"' + JSLINT.errors[i].reason + '", "line":' + JSLINT.errors[i].line + ', "character":' + JSLINT.errors[i].character + '}');
					}
				}
			}
			
			process.stdout.write(out);
		''')
		tmpfile.close()
		
		# store in tmp file
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
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
				tmperr = { 
					'line': int(tmpparts[0]), 
					'char': int(tmpparts[1]), 
					'text': tmpparts[2] 
				}
				tmperr['text'] = re.sub(r'^\"','', tmperr['text'])
				tmperr['text'] = re.sub(r'\"$','', tmperr['text'])
				elist.append( tmperr )
		
		self.create_bottom_tab()
		self.populate_bottom_tab(elist)
		

	# -------------------------------------------------------------------------------	
	# js beautify button click
	def on_format_js_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
		
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
		formatted_js = self.get_formatted_js_str(doctxt)
		
		#print result
		self.handle_new_output("Formatted JS Copied to Clipboard.", formatted_js)
		
	
	# -------------------------------------------------------------------------------	
	# js minify button click
	def on_minifier_js_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
			
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
		min_js = self.get_minified_js_str(doctxt)
		
		self.handle_new_output("Minified JS Copied to CLipboard", min_js)	


	# -------------------------------------------------------------------------------
	# js batch minify button click (choose several files and minify them all)
	def on_batch_minifier_js_activate(self, action):
		
		self.get_batch_minify_files_str('Javascript Files', 'js')

		return	

	# -------------------------------------------------------------------------------
	# css lint button click
	def on_lint_css_activate(self, action):
		doc = self._window.get_active_document()
		self.tab = self._window.get_active_tab()
		if not doc:
			return
		
		csslint_path = os.path.join(self.plugin_dir, "csslint-node")
		tmpfile_path = os.path.join(self.plugin_dir, "tmp_csslint.js")
		tmpcode_path = os.path.join(self.plugin_dir, "tmp_csslint_code.js")
		
		tmpfile = open(tmpfile_path,"w")
		tmpfile.writelines("var sys = require('sys');")
		tmpfile.writelines("var fs = require('fs');")
		tmpfile.writelines("var CSSLint = require('" + csslint_path + "').CSSLint;")
		tmpfile.writelines("var body = fs.readFileSync('" + tmpcode_path + "');")
		tmpfile.write('''
			body = body.toString("utf8");
			var result = CSSLint.verify(body);
			var msgs = result.messages;
			var errors = [];
			var out = '';
			
			if(msgs){
				for(var i=0, len=msgs.length; i<len; i++){
					out += msgs[i].line +','+ msgs[i].col +',"'+ msgs[i].type +': '+ msgs[i].message.toString().replace('"','\"') +'"\\n';
					errors.push('{"message":"' + msgs[i].type +': '+ msgs[i].reason + '", "line":' + msgs[i].line + ', "col":' + msgs[i].col + '}');
				}
			}
			
			process.stdout.write(out);
		''')
		tmpfile.close()
		
		# store in tmp file
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
		tmpcode = open(tmpcode_path,"w")
		tmpcode.write(doctxt)
		tmpcode.close()
		
		# run validation
		result = self._get_cmd_output(self._settings['nodejs'] +' ' + tmpfile_path)
		
		#clean up
		os.remove(tmpcode_path)
		os.remove(tmpfile_path)
		
		# we need to format it for our populate routine
		csslint_results = result.splitlines()
		elist = []
		for e in csslint_results:
			tmpparts = e.split(',')#re.split(r'\s*("[^"]*"|.*?)\s*,',e)
			if len(tmpparts) > 0:
				tmperr = { 
					'line': int(tmpparts[0]), 
					'char': int(tmpparts[1]), 
					'text': tmpparts[2] 
				}
				tmperr['text'] = re.sub(r'^\"','', tmperr['text'])
				tmperr['text'] = re.sub(r'\"$','', tmperr['text'])
				elist.append( tmperr )
		
		self.create_bottom_tab()
		self.populate_bottom_tab(elist)
	
	
	# -------------------------------------------------------------------------------
	# css format button click
	def on_format_css_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
		
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
		formatted_css = self.get_formatted_css_str(doctxt)
        
		self.handle_new_output("Formatted CSS Copied to Clipboard.", formatted_css)
		
	
	# -------------------------------------------------------------------------------
	# css minify button click
	def on_minifier_css_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
			
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
		min_css = self.get_minified_css_str(doctxt)
		
		self.handle_new_output("Minified CSS Copied to Clipboard.", min_css)
	

	# -------------------------------------------------------------------------------
	# css batch minify button click (choose several files and minify them all)
	def on_batch_minifier_css_activate(self, action):
		
		self.get_batch_minify_files_str('CSS Files', 'css')
		
		return	
	

	# -------------------------------------------------------------------------------
	# gzip button click
	def on_minifier_gzip_activate(self, action):
		doc = self._window.get_active_document()
		if not doc:
			return
		
		docuri = doc.get_uri_for_display()
		docfilename = doc.get_short_name_for_display()
		doctxt = doc.get_text(doc.get_iter_at_line(0), doc.get_end_iter(), True)
		docfilenamegz = docfilename + '.gz'
		
		dialog = Gtk.FileChooserDialog(title=None,action=Gtk.FileChooserAction.SAVE,buttons=(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_SAVE,Gtk.ResponseType.OK))
		dialog.set_do_overwrite_confirmation(True)
		dialog.set_current_folder(os.path.split(docuri)[0])
		dialog.set_current_name(docfilenamegz)
		dialog.set_default_response(Gtk.ResponseType.OK)
       
		response = dialog.run()
		
		if response == Gtk.ResponseType.OK:
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
	# minify a string of css
	def get_minified_css_str(self, css):
		
		min_css = CSSMin().minify(css)
		
		return min_css	
	
	# -------------------------------------------------------------------------------
	# format a string of css
	def get_formatted_css_str(self, css):
		
		self._import_gedit_preferences()
		
		braces_new_line = (self._settings['braces_on_own_line'] == 'true')
		tab = self._settings['indent_char'] * int(self._settings['indent_size'])
			
		formatted_css = CSSMin().format(css, braces_new_line, tab)
			
		return formatted_css
	
	# -------------------------------------------------------------------------------
	# minify a string of js
	def get_minified_js_str(self, js):
		
		ins = StringIO(js)
		outs = StringIO()
		
		JavascriptMinify().minify(ins, outs)
		
		min_js = outs.getvalue()
		
		if len(min_js) > 0 and min_js[0] == '\n':
			min_js = min_js[1:]
		
		min_js = re.sub(r'(\n|\r)+','', min_js)
		
		return min_js
	
	# -------------------------------------------------------------------------------
	# format a string of js
	def get_formatted_js_str(self, js):
		
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
		''')
		tmpfile.close()
		
		# store in tmp file
		tmpcode = open(tmpcode_path,"w")
		tmpcode.write(js)
		tmpcode.close()
		
		# run command
		result = self._get_cmd_output(self._settings['nodejs'] +' ' + tmpfile_path)
		
		#clean up
		os.remove(tmpcode_path)
		os.remove(tmpfile_path)
		
		return result
	
	# -------------------------------------------------------------------------------
	# choose files, minify them, and return a string
	def get_batch_minify_files_str(self, filter_name, filter_type):
		
		app_inst = Gedit.App.get_default()
		active_window = app_inst.get_active_window()
		
		dialog = Gtk.Dialog("Select Files to Minify", active_window, 0, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK))
		dialog.set_default_size(400, -1)
		content_area = dialog.get_content_area()
		
		treestore = Gtk.TreeStore(str,str)
		treeview = Gtk.TreeView(treestore)
		treeview.set_size_request(400, 150)
		
		#column 1
		cell = Gtk.CellRendererText()
		col = Gtk.TreeViewColumn("File", cell, text=0)
		treeview.append_column(col)
		
		#column 2
		cell = Gtk.CellRendererText()
		col = Gtk.TreeViewColumn("Path", cell, text=1)
		treeview.append_column(col)

		self.treeview_setup_dnd(treeview)

		content_area.pack_start(treeview, expand=False, fill=False, padding=0)
		
		hb = Gtk.HBox(False)
		
		#add button
		img = Gtk.Image()
		img.set_from_stock(Gtk.STOCK_ADD, Gtk.IconSize.SMALL_TOOLBAR)
		btn_add = Gtk.Button()
		btn_add.set_image(img)
		#btn_add = gtk.Button(label="+")
		#btn_add.set_size_request(20, 20)
		btn_add.connect('clicked', self.treeview_add_clicked, treeview, filter_name, filter_type)
		vb = Gtk.VBox()
		vb.pack_start(btn_add, expand=False, fill=False, padding=0)
		hb.pack_start(vb, expand=False, fill=False, padding=0)
		
		#remove button
		img = Gtk.Image()
		img.set_from_stock(Gtk.STOCK_REMOVE, Gtk.IconSize.SMALL_TOOLBAR)
		btn_remove = Gtk.Button()
		btn_remove.set_image(img)
		#btn_remove = Gtk.Button(label="-")
		#btn_remove.set_size_request(20, 20)
		btn_remove.connect('clicked', self.treeview_remove_clicked, treeview)
		vb = Gtk.VBox()
		vb.pack_start(btn_remove, expand=False, fill=False, padding=0)
		hb.pack_start(vb, expand=False, fill=False, padding=0)
		
		content_area.pack_start(hb, expand=False, fill=False, padding=0)
		
		dialog.show_all()

		#kick start the batch by opening the file dialog
		self.treeview_add_clicked(btn_add, treeview, filter_name, filter_type)
		
		response = dialog.run()
		
		
		if response == Gtk.ResponseType.OK:
			model = treeview.get_model()
			filenames = []
			
			for r in model:
				filenames.append(r[1])
				
			if filenames:
				min_code = ''
				charset = ''
				charsetre = r'(@charset \".+\";)'
				
				for file in filenames:
					tmpcode = open(file,"r")
					tmpread = tmpcode.read()
					tmpcode.close()
					
					if filter_type == 'css':
						
						#if there is a charset, keep up with it so we can add only one per file
						tmpcharset = re.findall(charsetre, tmpread)
						if tmpcharset:
							charset = tmpcharset[0]
							tmpread = re.sub(charsetre, '', tmpread)
						
						tmpread = self.get_minified_css_str(tmpread)
						
					else:
						tmpread = self.get_minified_js_str(tmpread)
						
					min_code = min_code + '/* '+ os.path.basename(file) + ' */\n'+ tmpread + '\n\n'
				
				if charset != '':
					min_code = charset + '\n\n' + min_code;
					
				self.handle_new_output("Batched and Minified "+ filter_name +" Copied to Clipboard.", min_code.strip())
			
		dialog.destroy()
		
	#add items to the tree store
	def treeview_add_clicked(self, button, treeview, filter_name, filter_type):
		model = treeview.get_model()
		
		dialog = Gtk.FileChooserDialog("Choose "+filter_name, None, Gtk.FileChooserAction.OPEN, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
		dialog.set_default_response(Gtk.ResponseType.OK)
		dialog.set_select_multiple(True)
		
		filter = Gtk.FileFilter()
		filter.set_name(filter_name)
		filter.add_pattern("*."+ filter_type)
		dialog.add_filter(filter)

		response = dialog.run()
		
		if response == Gtk.ResponseType.OK:
			filenames = dialog.get_filenames()
			
			if filenames:
				for file in filenames:
					model.append(parent=None, row=[ os.path.basename(file), file ] )
					
		dialog.destroy()
	
	# remove items from the Treestore	
	def treeview_remove_clicked(self, button, treeview):
		model, source = treeview.get_selection().get_selected()
		if source:
			model.remove(source)
	
	# handle treeview drag and drop
	def treeview_setup_dnd(self, treeview):
		target_entries = [('example', Gtk.TargetFlags.SAME_WIDGET, 0)]
		treeview.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target_entries, Gdk.DragAction.MOVE)
		treeview.enable_model_drag_dest(target_entries, Gdk.DragAction.MOVE)
		treeview.connect('drag-data-received', self.treeview_on_drag_data_received)
	    
	def treeview_on_drag_data_received(self, treeview, drag_context, x, y, selection_data, info, eventtime):
		print "found dnd"
		target_path, drop_position = treeview.get_dest_row_at_pos(x, y)
		model, source = treeview.get_selection().get_selected()
		target = model.get_iter(target_path)
		if not model.is_ancestor(source, target):
			
			if drop_position == Gtk.TREE_VIEW_DROP_BEFORE:
				model.move_before(source, target)
			elif drop_position == Gtk.TREE_VIEW_DROP_AFTER:
				model.move_after(source, target)
				
			drag_context.finish(success=True, del_=False, time=eventtime)
		else:
			drag_context.finish(success=False, del_=False, time=eventtime)
	
	

		
	
	# -------------------------------------------------------------------------------
	# ask the user what to do with the output
	def handle_new_output(self, remark, contents):
		view = self._window.get_active_view()
		remark = remark +"\n\nDo you want to replace it in the document?"
		
		#save to clipboard
		self.clipboard.set_text(contents, len(contents))
		
		# do we want to overwrite current document?
		response = Gtk.ResponseType.NO
		
		# go ahead and replace it
		if self._settings['replace_contents'] == 1:
			response = Gtk.ResponseType.YES
		
		# ask what to do	
		elif self._settings['replace_contents'] == 2:
			md = Gtk.MessageDialog(self._window, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, remark)
			response = md.run()
			md.destroy()
		
		if response == Gtk.ResponseType.YES:
			
			# out with the old
			view.select_all()
			#view.delete_selection()
			
			# in with the new
			view.paste_clipboard()

	#================================================================================
	# Configuration Window
	#================================================================================
	def open_config_window(self, action=None):
		app_inst = Gedit.App.get_default()
		active_window = app_inst.get_active_window()
		
		dialog = Gtk.Dialog("Configure Gedit Clientside Plugin", active_window, 0, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK))
		dialog.set_default_size(300, -1)
		dialog.connect('response', self._save_config)
		content_area = dialog.get_content_area()

		table = Gtk.Table(5, 4, False)	
		table.set_row_spacings(8)	
		table.set_col_spacings(10)
		
		core_label = Gtk.Label()
		core_label.set_markup("<b>Core Settings</b>")
		core_label.set_alignment(xalign=0.0, yalign=0.5)
		table.attach(core_label, 1, 4, 0, 1 )
		
		nodejs_label = Gtk.Label()
		nodejs_label.set_markup("How do I call NodeJS?")
		nodejs_label.set_alignment(xalign=0.0, yalign=0.5)
		table.attach(nodejs_label, 2, 3, 1, 2 )
		
		self.config_fields['nodejs'] = Gtk.Entry()
		self.config_fields['nodejs'].set_text(self._settings['nodejs'])
		table.attach(self.config_fields['nodejs'], 3, 4, 1, 2 )

		
		after_label = Gtk.Label()
		after_label.set_markup("What do I do after I Minify or Format your code?")
		after_label.set_alignment(xalign=0.0, yalign=0.5)
		table.attach(after_label, 2, 4, 3, 4 )
		
		self.config_fields['replace_contents_0'] = Gtk.RadioButton.new_with_label_from_widget(None, "Copy to clipboard")
		if self._settings['replace_contents'] == 0:
			self.config_fields['replace_contents_0'].set_active(True)
		else:
			self.config_fields['replace_contents_0'].set_active(False)
		table.attach(self.config_fields['replace_contents_0'], 2, 4, 4, 5 )
		
		self.config_fields['replace_contents_1'] = Gtk.RadioButton.new_with_label_from_widget(self.config_fields['replace_contents_0'], "Replace the current file")
		if self._settings['replace_contents'] == 1:
			self.config_fields['replace_contents_1'].set_active(True)
		else:
			self.config_fields['replace_contents_1'].set_active(False)
		table.attach(self.config_fields['replace_contents_1'], 2, 4, 5, 6 )
		
		self.config_fields['replace_contents_2'] = Gtk.RadioButton.new_with_label_from_widget(self.config_fields['replace_contents_0'], "Ask me")
		if self._settings['replace_contents'] == 2:
			self.config_fields['replace_contents_2'].set_active(True)
		else:
			self.config_fields['replace_contents_2'].set_active(False)
		table.attach(self.config_fields['replace_contents_2'], 2, 4, 6, 7 )

		
		formatting_label = Gtk.Label()
		formatting_label.set_markup("<b>Formatting</b>")
		formatting_label.set_alignment(xalign=0.0, yalign=0.5)
		table.attach(formatting_label, 1, 4, 7, 8 )
		
		self.config_fields['braces_on_own_line'] = Gtk.CheckButton("Place braces on a new line")
		if self._settings['braces_on_own_line'] == "true":
			self.config_fields['braces_on_own_line'].set_active(True)
		table.attach(self.config_fields['braces_on_own_line'], 2, 4, 8, 9 )
		
		content_area.pack_start(table, expand=False, fill=False, padding=10)
		
		
		dialog.show_all()
		
		# from gedit preferences
		if action is None:
			return dialog

		# from tools menu...
		response_id = dialog.run()
		
	def _save_config(self, dialog, response_id):
		if response_id == Gtk.ResponseType.OK:
			
			# where is nodejs
			self._settings['nodejs'] = self.config_fields['nodejs'].get_text()
			
			# what to do when format or minify
			if self.config_fields['replace_contents_0'].get_active():
				self._settings['replace_contents'] = 0
			elif self.config_fields['replace_contents_1'].get_active():
				self._settings['replace_contents'] = 1
			else:
				self._settings['replace_contents']=2
			
			# when formatting put braces on new line?	
			if self.config_fields['braces_on_own_line'].get_active():
				self._settings['braces_on_own_line'] = "true"
			else:
				self._settings['braces_on_own_line'] = "false"
			
			self._write_config_file(self._settings)
		
		dialog.destroy()
		
	def _read_config_file(self):
		
		#if file doesn't exist, create it.. write defaults return
		if not os.path.exists(self.config_store):
			self._write_config_file(self._settings)
			return self._settings
		
		pkl_file = open(self.config_store, 'rb')
		self._settings = pickle.load(pkl_file)
		pkl_file.close()
		
		return self._settings
	
	def _write_config_file(self, settings):
				
		output = open(self.config_store, 'wb')
		pickle.dump(settings, output)
		output.close()

		return	


class ClientsidePlugin(GObject.Object, Gedit.WindowActivatable, PeasGtk.Configurable):
	__gtype_name__ = "ClientsidePlugin"
	window = GObject.property(type=Gedit.Window)
	
	def __init__(self):
		GObject.Object.__init__(self)
		self._instances = {}
		
	def do_activate(self):
		self._instances[self.window] = ClientsideWindowHelper(self, self.window)

	def do_deactivate(self):
		self._instances[self.window].deactivate()
		del self._instances[self.window]

	def do_update_state(self):
		self._instances[self.window].update_ui()
		
	def do_create_configure_widget(self):
		#return self._instances[self.window].open_config_window()
		widget = Gtk.Label("Please update this plugin from the Tools->Clientside menu.")
		return widget

