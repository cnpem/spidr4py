#!/usr/bin/env python3

#############################################################################################################
#
#  hdf5.py
#
#  A hdf5 class to store Spidr4 data in a Nexus standard format
#
#  Authors:
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  March 2026
#
#############################################################################################################

from datetime import datetime
import numpy as np
import sys
import os

from nexusformat.nexus import (NXdata, NXdetector, NXentry, NXfield,
                               NXinstrument, NXcollection, nxopen)

class hdf5_nexus:
  def __init__(self,filepath,swmr_mode=True,serial_number='0',metadata={}):

    self.filepath = filepath
    self.swmr_mode = swmr_mode

    self.det_size = (512,448)

    print(f"Create file: {self.filepath}")
    # create the HDF5 NeXus file
    self.file = nxopen(filepath,'w',libver='latest')

    self.file["entry"] = NXentry(
      program_name=os.path.basename(sys.argv[0]),
      start_time = datetime.now().astimezone().isoformat(timespec='seconds')
      )

    self.file["entry/instrument"] = NXinstrument()
    self.file["entry/instrument/detector"] = NXdetector(
      detector_number = self.det_size,
      description = 'Nikhef Spidr4 Timepix4',
      serial_number = f'{serial_number}',
    )

    # store the data in the NXdetector group
    self.file["entry/instrument/detector/data"] = NXfield(np.ones((0,self.det_size[0],self.det_size[1])),maxshape=(None,self.det_size[0],self.det_size[1]), units="counts", chunks=True, name= 'data',dtype=np.uint64)

    # create a dataset for CRWframes
    self.file["entry/instrument/detector/CRWframes"] = NXfield(np.ones((0,self.det_size[0],self.det_size[1])),maxshape=(None,self.det_size[0],self.det_size[1]), units="counts", chunks=True, name= 'CRWframes',dtype=np.uint16)

    # Make detector/data the main data of the file, opening as default
    self.file["entry/data"] = NXdata()
    self.file["entry/data"].makelink(self.file["entry/instrument/detector/data"])
    self.file['entry/data'].nxsignal = self.file['entry/data/data']
    self.file["entry/data"].set_default()

    # Create the metadata collection
    self.metadata = self.file['entry/instrument/metadata'] = NXcollection()

    #Write optional metadata
    self.write_metadata(metadata)

    # Turn on swmr (Single Writer Multiple Reader)
    # See https://docs.h5py.org/en/latest/swmr.html
    self.file.swmr_mode = self.swmr_mode
    # Now is safe to the reader open the hdf5 file

  def append_image(self,img,field='data'):
    # Append only if the image fits the expected size
    if img.shape == self.det_size:
      #Resize the dataset
      self.file[f"entry/instrument/detector/{field}"].resize(self.file[f"entry/instrument/detector/{field}"].shape[0]+1,axis=0)
      #Append the image to the resized array
      self.file[f"entry/instrument/detector/{field}"][-1:] = img
    else:
      print(f'Shape {img.shape} not supported. Please use {self.det_size}')
      sys.exit(1)

  def write_metadata(self,metadata = {}):
    if len(metadata) > 0:
      # write to /entry/instrument/metadata
      for k, v in metadata.items():
          self.metadata[k] = v

  def close(self):
    self.file["entry"].end_time = datetime.now().astimezone().isoformat(timespec='seconds')
    #Explicitly closes the HDF5 file
    if self.file:
      self.file.close()
      print(f"File {self.filepath} closed.")

  # Optional: Implement context manager capabilities for automatic cleanup
  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()

# -----------------------------------------------------------------------------------------------------------
# This module can be called as main to test hdf5 file creation with SWMR
if __name__=="__main__":

  import numpy as np
  import time

  # Create the output file
  outfile = hdf5_nexus('test.hdf5')

  # Create a metadata dictionary
  meta = {
    'Greetings':'Hello',
    'Nexus Test': 'Thanks',
    'Great':'Awesome',
    'Number':4,
    'Float':5.2,
  }

  # Write metadata to the file
  outfile.write_metadata(meta)

  # Add images to the hdf5 file
  for i in range(21):
    print(f'Add image index {i}')
    img = np.ones((512,448))*i
    # Append a few images to data field
    if i%5 == 0:
      outfile.append_image(img,field='data')
    # Append all images to CRW frames
    outfile.append_image(img,field='CRWframes')
    time.sleep(1)

  # Close the file and end the script
  outfile.close()

