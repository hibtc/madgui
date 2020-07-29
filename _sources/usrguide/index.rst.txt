User's guide
============

Welcome to the user's guide. We expect madgui to be intuitive, but for
full usability of the implemented features here is a detailed description
of how to optimaly format a model suiting madgui's necessities.
Please make sure to take a look at the following sections describing madgui's
standard menu options as well as the window arrays.

.. toctree::
  mainWindow
  model
  view
  exportImport
  settings
  online
  help

Setting up the model
--------------------

As you might already have noticed, the way you can format your model in
MAD-X is quite broad. For this reason some compromises were met in order to
give a smooth structure for madgui to access every parameter in the lattice.
We are going to assume you already have your model and that it runs in the latest
version of MAD-X.

Since the applications of MAD-X are quite broad, we will show an example of a
lattice that was already designed in the sense that the length of the magnets
and drifts won't change, but the focussing strenghts of the quadrupoles or in
general the K-values of the multipoles are still to be tuned.

In principle the length of the magnets can also be varied, but this exercise
is left to the user interested in this application.


Set-up file
###########
  
First make a new work folder, e.g. sample Model, and open a new text file.
The text file will contain following information::

  path: Name of the folder containing the beam line model
  init-files:
    - File containing the initial element strengths
    - File containing the sequence of the beam line
  sequence: Name of the sequence that will be used
  range: From where to where will the model run
  beam: File containing the modeled beam
  twiss:
    Initial twiss parameters

The following is an example that you can find in `sample model`_::

  path: beamLine
  init-files:
   - strengths.str
   - sequence.madx
     
  sequence: beamline1
  range: ['#s', '#e']

  beam: "../shared/beamSample.yml"

  twiss:
    betx: 1.
    bety: 1.
    alfx: 0.
    alfy: 0.

Note that the name of the folder containing the beam line is **beamLine**,
the sequence name is **beamline1** and the beam file is in a folder called
**shared**, but we will come to that later. The file containing the beam line
definition must in fact be called **"sequence.madx"**. 
Save this file as **"sample.cpymad.yml"**.
The file extension **'.cpymad.yml'** will be recognized automatically by madgui, but you might
as well use any extension of your choice.
Note that all the file paths will be relative to the path of **beamLine** folder.

Beam file
#########

As we can see from the set up file, the beam definition is in a file called
**"beamSample.yml"** inside a folder called **shared**. The beam file should look
as follows::

  particle: C
  mass:   11.177929     # 12u = 12*931.494095457e-3
  energy: 16.337929     # 12u + 12*430MeV
  charge: 6.0
  ex: 1.0e-06
  ey: 1.0e-06
  sigt: 0.001
  sige: 0.001
  radiate: false

Notice that we defined a Carbon Ion beam with 430MeV.
  
Reformating the sequence
########################

The next step is to reformat your sequence for madgui to understand it better.
The parameters of the elements in the sequence that are to be tuned, for
example, the quadrupole strengths or the kick angle of orbit corrector magnets
will be in the **"strengths.str"** file, whereas the static parameters such as the
length of the magnets and drifts or the bending angles of the dipoles,
will be written directly on the definition of the beam line sequence.

In the `sample model`_ we have 3 quadrupole families, two bending magnets,
two corrector kickers and two monitors. The **'strengths.str'** has following
information::
  
   ! These are the nominal K-values of the quadrupoles
   ! First quadrupole duplet
   kL_Q11 = 1.0;
   kL_Q12 = -1.0;
   ! Second quadrupole duplet
   kL_Q21 = 1.0;
   kL_Q22 = -1.0;
   ! Third quadrupole duplet
   kL_Q31 = 1.0;
   kL_Q32 = -1.0;
   ! These are the kick nominal values
   ax_K1  = 0.000;
   ay_K1  = 0.000;

Now you just have to make sure that the parameters have the same name in the
sequence file, and are defined with ':', in the sample the sequence file look
as follows::

  call, file="../shared/defs.madx";
  ! This is practical if you want to divide your sequences in smaller parts 
  beamline1: sequence, refer=entry, L=22.0;
    call, file="sampleSeq1.seq";
    call, file="sampleSeq2.seq";
  endsequence;

where you can easily see that the sequence was divided in two parts,
the first part is in the file **'sampleSeq1.seq'** and the second in
**'sampleSeq2.seq'**. A file named **'defs.madx'** was called and it
is on the folder named **'shared'**. This might be practical if you share
values for different transfer lines or models.
The definition of the first part of the sequence as in **'sampleSeq1.seq'**
look as follows::

  ! These are the fixed lengths of the
  ! two quadrupole families
  const L_Q11 = 0.50;
  const L_Q12 = 0.50;
  const L_Q21 = 0.50;
  const L_Q22 = 0.50;

  INIT:       DRIFT, L=1.0, at=0.0;
  QUAD_11:    QUADRUPOLE, L=L_Q11, k1:=kL_Q11/L_Q11, at=1.0;
  O_11:       DRIFT, L=0.3, at=1.5;
  QUAD_12:    QUADRUPOLE, L=L_Q12, k1:=kL_Q12/L_Q12, at=1.8;
  O_12:       DRIFT, L=2.7, at=2.3;
  QUAD_21:    QUADRUPOLE, L=L_Q21, k1:=kL_Q21/L_Q21, at=5.0;
  O_13:       DRIFT, L=0.3, at=5.5;
  QUAD_22:    QUADRUPOLE, L=L_Q22, k1:=kL_Q22/L_Q22, at=5.8;
  O_14:       DRIFT, L=1.2, at=6.3;
  MONITOR1:   MONITOR, at=7.5;
  O_15:       DRIFT, L=2.5, at=7.5;

Notice here that in k1, the parameter was defined with **':='**
and not with **'='**. Essentially it is a quite trivial task to reformat
your beam line. Make sure to experiment with the template format in
the sample model and consider that this is just a set of soft guidelines,
but remember that any sequence that runs in MAD-X, will also run in madgui,
as long as the Twiss command was called once. 
  
.. _`sample model` : https://github.com/hibtc/sample_model

  

