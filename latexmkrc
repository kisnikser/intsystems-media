$pdf_mode = 5;
# Packages and the beamer theme live in sty/.
ensure_path('TEXINPUTS', './sty//');
$xelatex = 'xelatex -interaction=nonstopmode -synctex=1 %O %S';

push @generated_exts, 'zip';

END {
  # Only the covers build exports PNGs.
  return if $root_filename eq 'presentation';
  my $pdf = -e 'output.pdf' ? 'output.pdf' : 'main.pdf';
  return unless -e $pdf;
  system(
    'gs', '-dBATCH', '-dNOPAUSE', '-dQUIET',
    '-sDEVICE=png16m', '-g1920x1080', '-dPDFFitPage', '-dUseCropBox',
    '-sOutputFile=cover-%d.png', $pdf
  );
  my @png = glob('cover-*.png');
  system('zip', '-j', 'covers-png.zip', @png) if @png;
  unlink @png;
}
