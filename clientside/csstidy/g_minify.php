<?php
	include('class.csstidy.php');
	
	$css_file = "tmp_csstidy_code.css";
	
	$f = fopen($css_file, "r");
	$css_code = fread($f, filesize($css_file));
	fclose($f);



	$css = new csstidy();
	$css->load_template("highest_compression");
	
	$css->set_cfg('remove_last_;',TRUE);

	$css->parse($css_code);

	print $css->print->plain();

?>
