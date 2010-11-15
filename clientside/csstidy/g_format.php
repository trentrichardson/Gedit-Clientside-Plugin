<?php
	include('class.csstidy.php');
	
	$css_file = "tmp_csstidy_code.css";
	
	$f = fopen($css_file, "r");
	$css_code = fread($f, filesize($css_file));
	fclose($f);



	$css = new csstidy();
	$css->load_template("low_compression");
	
	$css->set_cfg('preserve_css', true);
	$css->set_cfg('compress_colors', false);

	$css->parse($css_code);

	print $css->print->plain();

?>
