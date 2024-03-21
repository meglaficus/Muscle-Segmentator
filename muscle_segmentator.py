import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import tkinter.scrolledtext as ScrolledText
import sys
import SimpleITK as sitk
import os
import nibabel as nib
from totalsegmentator.python_api import totalsegmentator
import numpy as np
import multiprocessing

if getattr(sys, 'frozen', False):
    import pyi_splash

class OutputRedirector(object):
    def __init__(self, text_widget):
        self.text_space = text_widget

    def write(self, message):
        if message.strip().endswith('/it]') or message.strip().endswith('/s]'):
            self.text_space.delete("end-1l", "end")
            self.text_space.insert(tk.END, '\n')
            
            self.text_space.insert(tk.END, message)
        else:
            self.text_space.insert(tk.END, message)

        self.text_space.see(tk.END)  # Scroll to the end of the text widget
        # self.text_space.delete(1.0, tk.END)
        self.text_space.update()

    def flush(self):
        pass  # This is required to satisfy the sys.stdout interface

class EntryBox(ttk.Entry):
    def __init__(self, master, width, input_text):
        ttk.Entry.__init__(self, master=master, width=width)
        self.input_text = input_text
        self.insert(0, input_text)
        
        def temp_text_in(e):
            if self.get() == input_text:
                self.delete(0,"end")

        def temp_text_out(e):
            if not self.get():
                self.insert(0, self.input_text)
        
        self.bind("<FocusIn>", temp_text_in)
        self.bind("<FocusOut>", temp_text_out)

class DirectoryBrowseButton(ttk.Button):
    def __init__(self, parent, target_widget, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.target_widget = target_widget
        self.config(command=self.open_input_directory)

    def open_input_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.target_widget.delete(0, tk.END)
            self.target_widget.insert(0, directory)

class NiftiBrowseButton(ttk.Button):
    def __init__(self, parent, target_widget, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.target_widget = target_widget
        self.config(command=self.open_file)

    def open_file(self):
        file = filedialog.askopenfilenames(filetypes=[('nifti','*.nii *.nii.gz')])
        if file:
            self.target_widget.delete(0, tk.END)
            self.target_widget.insert(0, file)


def run_my_program():
    input_directory0 = input_entry.get()
    output_directory = output_entry.get()
    segment_path = segmentation_entry.get()
    
    entered_input = input_directory0 != 'DICOM directory'
    entered_output = output_directory != 'Output directory'
    entered_segment = segment_path != 'Segmentation file path'
    
    
    if entered_input:
        input_directory =  os.path.join(input_directory0, os.listdir(input_directory0)[0])
    
    device = dropdown2.get().lower()
    size = dropdown.get()
    
    muscles = class_listbox.curselection()
    
    print('-------------------------------------------------')
    print('')

    if (entered_input and entered_output) and not entered_segment:
        print('Finding DICOM')
        flag = False
        for folder in [os.path.join(input_directory, i) for i in os.listdir(input_directory)]:
            if flag:
                break
            try:
                reader = sitk.ImageSeriesReader()
                filename_reader = sitk.ImageFileReader()

                study_id_key = '0008|0050'
                study_name_key = '0008|103e'

                dicom_names = reader.GetGDCMSeriesFileNames(folder)
                reader.SetFileNames(dicom_names)
                filename_reader.SetFileName(dicom_names[0])
                
                filename_reader.LoadPrivateTagsOn()
                filename_reader.ReadImageInformation()      

                study_id = filename_reader.GetMetaData(study_id_key).strip()
                study_name = filename_reader.GetMetaData(study_name_key).strip()

                print(f'Working on {study_id} ({study_name})')
                image = reader.Execute()
                flag = True

            except:
                print(f'{folder} was a dead end')
                print('')
        if not flag:
            print('No usable files found, exiting.')
            raise RuntimeError

        print('Saving CT nifti')
        nifti_path = os.path.join(output_directory, f'{study_id}_CT.nii.gz')
        sitk.WriteImage(image, nifti_path)
        print('Saved!')        
        
        print('Starting segmentation')
        
        input_img = nib.load(nifti_path)
        if size == '1.5 mm':
            segment = totalsegmentator(input_img, 'output', skip_saving=True, device=device, fast=False)
        else:
            segment = totalsegmentator(input_img, 'output', skip_saving=True, device=device, fast=True)
            
        print('Saving segmentation...')
        segment_path = os.path.join(output_directory, f'{study_id}_segmentation.nii.gz')
        nib.save(segment, segment_path)
        
        seg_img = sitk.ReadImage(segment_path)
        seg_array = sitk.GetArrayFromImage(seg_img)
        muscle_array = np.zeros_like(seg_array)
        
        for i in range(80, 90):
            muscle_array[seg_array == i] = i
    	
        muscle_image = sitk.GetImageFromArray(muscle_array)
        muscle_image.CopyInformation(seg_img)
        sitk.WriteImage(muscle_image, segment_path)

        print('Saved!')
        
    elif entered_segment:
        print('Using segmentation file')
        print('')

        
    if entered_segment or (entered_input and entered_output):
        
        segment_img = sitk.ReadImage(segment_path)
        segment_array = sitk.GetArrayFromImage(segment_img)
        
        # print(segment_array.shape)
        # print(segment_array[0].shape)
        
        spacing = segment_img.GetSpacing()
        voxel_volume = spacing[0] * spacing[1] * spacing[2]
        # print(f'spacing = {spacing}')
        # print(f'voxel volume = {voxel_volume} mm\u00B3')
        
        print('-------------------------------------------------')
        print('')
        
        muscles_task = []
        
        for muscle_no in muscles:
            muscles_task += muscles_dict[muscle_no]
        
        for muscle in muscles_task:
            array = np.zeros_like(segment_array)
            array[segment_array == segmentations_dict[muscle]] = 1
            muscle_volume = round(int(np.sum(array.flatten()) * voxel_volume)/1000, 1)

            if np.count_nonzero(array[0]) or np.count_nonzero(array[-1]):
                print(f'{muscle_name_dict[muscle]} = {muscle_volume} cm\u00B3     |     Warning! Muscle is clipped!')

            else:
                print(f'{muscle_name_dict[muscle]} = {muscle_volume} cm\u00B3')

    else:
        print('please choose input and output directories or specify segmentation path!')
        
    if not muscles:
        print('please choose muscles to measure')
        

if __name__ == '__main__':
    multiprocessing.freeze_support()
    
    # Create the main window
    root = tk.Tk()
    big_frame = ttk.Frame(root)
    big_frame.pack(fill="both", expand=True)
    
    if getattr(sys, 'frozen', False):
        pyi_splash.close()

    # Set the initial theme
    root.tk.call("source", "azure.tcl")
    root.tk.call("set_theme", "dark")
    
    root.title("Muscle segmentator \U0001F4AA")

    # Input Directory Section
    input_entry = EntryBox(big_frame, width=80, input_text='DICOM directory')
    input_entry.grid(row=0, column=0, padx=5, pady=5)

    input_browse_button = DirectoryBrowseButton(big_frame, input_entry, text="Browse", width=11)
    input_browse_button.grid(row=0, column=1, padx=5, pady=5)

    # Output Directory Section
    output_entry = EntryBox(big_frame, width=80, input_text='Output directory')
    output_entry.grid(row=1, column=0, padx=5, pady=5)

    output_browse_button = DirectoryBrowseButton(big_frame, output_entry, text="Browse", width=11)
    output_browse_button.grid(row=1, column=1, padx=5, pady=5)
    
    # OR label
    or_label = ttk.Label(big_frame, text="OR")
    or_label.grid(row=2, column=0, padx=5, pady=5)

    # Segmentation File Section
    segmentation_entry = EntryBox(big_frame, width=80, input_text='Segmentation file path')
    segmentation_entry.grid(row=3, column=0, padx=5, pady=5)

    segmentation_browse_button = NiftiBrowseButton(big_frame,segmentation_entry, text="Browse", width=11)
    segmentation_browse_button.grid(row=3, column=1, padx=5, pady=5)
    
    # Output Window
    font_tuple = ("Fira Code", 9) 
    
    output_window = ScrolledText.ScrolledText(big_frame, height=18, width=80)
    output_window.grid(row=4, rowspan=5, column=0, padx=5, pady=5)
    output_window.configure(font=font_tuple)

    # Redirect stdout to text widget
    sys.stdout = OutputRedirector(output_window)
    sys.stderr = OutputRedirector(output_window)
    
    # Dropdown Menu
    options = ["1.5 mm", "3 mm"]  # Add your options here
    dropdown_var = tk.StringVar()
    dropdown = ttk.Combobox(big_frame, textvariable=dropdown_var, state="readonly", values=options, width=12)
    dropdown.grid(row=4, column=1)
    dropdown.current(1)  # Set the default selection
    
    options2 = ["CPU", "GPU"]  # Add your options here
    dropdown_var2 = tk.StringVar()
    dropdown2 = ttk.Combobox(big_frame, textvariable=dropdown_var2, state="readonly", values=options2, width=12)
    dropdown2.grid(row=5, column=1)
    dropdown2.current(0)  # Set the default selection
    
    classes = [
        "Gluteus Maximus", "Gluteus Medius", "Gluteus Minimus", "Paravertebral", "Iliopsoas"
    ]
    
    muscles_dict = {0:['gluteus_maximus_left','gluteus_maximus_right'],
                    1:['gluteus_medius_left','gluteus_medius_right'],
                    2:['gluteus_minimus_left','gluteus_minimus_right'],
                    3:['autochthon_left','autochthon_right'],
                    4:['iliopsoas_left','iliopsoas_right']}
    
    segmentations_dict = {'gluteus_maximus_left':	80,
                          'gluteus_maximus_right':	81,
                          'gluteus_medius_left':	82,
                          'gluteus_medius_right':	83,
                          'gluteus_minimus_left':	84,
                          'gluteus_minimus_right':	85,
                          'autochthon_left':        86,
                          'autochthon_right':	    87,
                          'iliopsoas_left':	        88,
                          'iliopsoas_right':	    89
                          }
    
    muscle_name_dict = {  'gluteus_maximus_left':	'Left Gluteus Maximus',
                          'gluteus_maximus_right':	'Right Gluteus Maximus',
                          'gluteus_medius_left':	'Left Gluteus Medius',
                          'gluteus_medius_right':	'Right Gluteus Medius',
                          'gluteus_minimus_left':	'Left Gluteus Minimus',
                          'gluteus_minimus_right':	'Right Gluteus Minimus',
                          'autochthon_left':        'Left Paravertebral',
                          'autochthon_right':	    'Right Paravertebral',
                          'iliopsoas_left':	        'Left Iliopsoas',
                          'iliopsoas_right':	    'Right Iliopsoas'
                          }
    

    class_listbox = tk.Listbox(big_frame, selectmode=tk.MULTIPLE, width=15, height=5)
    for c in classes:
        class_listbox.insert(tk.END, c)
        
    class_listbox.grid(row=6, column=1, padx=5, pady=5, sticky="nsew")

    # Run Button
    run_button = ttk.Button(big_frame, text="Run", command=run_my_program, style='Accent.TButton')
    run_button.grid(row=8, column=1, padx=5, pady=5)

    # Start the Tkinter event loop
    root.mainloop()