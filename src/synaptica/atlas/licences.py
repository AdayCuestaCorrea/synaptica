"""Licence, source and citation of every atlas file Neuro Atlas serves.

Copied from ``spikes/s3/build_assets.py`` (spike S3, Phase 0) for Neuro Atlas (Phase 2,
SCOPE v160); the ``derived`` notes of Waxholm and Julich-Brain no longer mention the meshes of
mock-up B. Each atlas is written to its own folder with its ``licence.json``; the website shows
them (CLAUDE.md, "Licencias"). Julich-Brain's citation is completed from siibra at build time.
"""

from __future__ import annotations

ICBM_WM_MIN = 0.5  # white matter probability, and higher than grey matter and CSF

LICENCES = {
    "bigbrain": {
        "atlas": "BigBrain, Merker-stained histology, in ICBM152 2009 nonlinear asymmetric space",
        "short": "BigBrain (1 mm, ICBM152 2009)",
        "version": "BigBrain 2015 release, registration by Xiao et al. 2019",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "licence_note": (
            "The down-sampled BigBrain volumes of this OSF dataset are CC BY 4.0 with the consent "
            "of the MNI and Forschungszentrum Jülich; BigBrain itself remains CC BY-NC-SA 4.0 "
            "(README of the dataset)."
        ),
        "source": "OSF project xkqb3, file BigBrain-to-ICBM2009asym-nonlin-1mm.nii",
        "source_url": "https://osf.io/xkqb3/",
        "citation": (
            "Amunts K. et al. 2013, BigBrain: an ultrahigh-resolution 3D human brain model, "
            "Science 340:1472-1475, https://doi.org/10.1126/science.1235381; Xiao Y. et al. 2019, "
            "An accurate registration of the BigBrain dataset with the MNI PD25 and ICBM152 "
            "atlases, Scientific Data 6:210, https://doi.org/10.1038/s41597-019-0217-0"
        ),
        "derived": (
            "Converted to 8 bits; slide (white) and voxels without data set to 0 so that they "
            "are transparent; centred like the Julich-Brain label volume (same grid). Changes "
            "made by SYNAPTICA. Not combined with any atlas file."
        ),
    },
    "cerebra": {
        "atlas": "CerebrA, Mindboggle-101 labels registered to MNI-ICBM2009c and corrected by hand",
        "short": "CerebrA",
        "version": "G-Node GIN release, DOI 10.12751/g-node.be5e62",
        "licence": "CC0 1.0 (labels from Mindboggle-101, CC BY-NC-SA 3.0)",
        "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "licence_note": (
            "The CerebrA repository is CC0 1.0 (datacite.yml and LICENSE). Its labels derive from "
            "Mindboggle-101, which NITRC lists as CC BY-NC-SA 3.0; SYNAPTICA follows the stricter "
            "of the two, which it allows (NC licences are accepted)."
        ),
        "source": "G-Node GIN, CerebrA.nii and CerebrA_LabelDetails.csv",
        "source_url": "https://doi.org/10.12751/g-node.be5e62",
        "citation": (
            "Manera A. L., Dadar M., Fonov V., Collins D. L. 2020, CerebrA, registration and "
            "manual label correction of Mindboggle-101 atlas for MNI-ICBM152 template, "
            "Scientific Data 7:237, https://doi.org/10.1038/s41597-020-0557-9; Klein A., "
            "Tourville J. 2012, 101 labeled brain images and a consistent human cortical "
            "labeling protocol, Frontiers in Neuroscience 6:171, "
            "https://doi.org/10.3389/fnins.2012.00171"
        ),
        "derived": (
            "Only the structures with at least half of their voxels outside Julich-Brain, and only "
            "those voxels (layers.py); compact indices per structure and side; centred like the "
            "Julich-Brain label volume (same grid). Changes made by SYNAPTICA. Not combined with "
            "any Julich-Brain file: the viewer only shows one under the other."
        ),
    },
    "cit168": {
        "atlas": "CIT168 subcortical atlas (Reinforcement Learning Atlas), deterministic map in "
        "MNI152 2009c nonlinear asymmetric",
        "short": "CIT168",
        "version": "v1.1.0",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "source": "OSF project jkzwp, CIT168toMNI152-2009c_det.nii.gz and labels.txt",
        "source_url": "https://osf.io/jkzwp/",
        "citation": (
            "Pauli W. M., Nili A. N., Tyszka J. M. 2018, A high-resolution probabilistic in vivo "
            "atlas of human subcortical brain nuclei, Scientific Data 5:180063, "
            "https://doi.org/10.1038/sdata.2018.63"
        ),
        "derived": (
            "Split into left and right at the midline; only the structures with at least half "
            "of their voxels outside Julich-Brain and CerebrA, and only those voxels (layers.py); "
            "compact indices; centred like the Julich-Brain label volume (same grid). Changes "
            "made by SYNAPTICA. Not combined with any other atlas file."
        ),
    },
    "icbm_wm": {
        "atlas": "ICBM 2009c nonlinear asymmetric template, white matter probability map",
        "short": "ICBM152 2009c",
        "version": "2009c nonlinear asymmetric, 1 mm",
        "licence": "Copyright (C) 1993-2004 Louis Collins, McConnell Brain Imaging Centre, "
        "Montreal Neurological Institute, McGill University (free use with this notice)",
        "licence_url": "https://nist.mni.mcgill.ca/icbm-152-nonlinear-atlases-2009/",
        "licence_note": (
            "COPYING of the template: permission to use, copy, modify, and distribute for any "
            "purpose and without fee, provided that the copyright notice appears in all copies."
        ),
        "source": "mni_icbm152_nlin_asym_09c_nifti.zip, mni_icbm152_wm_tal_nlin_asym_09c.nii",
        "source_url": "https://nist.mni.mcgill.ca/icbm-152-nonlinear-atlases-2009/",
        "citation": (
            "Fonov V. et al. 2011, Unbiased average age-appropriate atlases for pediatric "
            "studies, NeuroImage 54:313-327, https://doi.org/10.1016/j.neuroimage.2010.07.033"
        ),
        "derived": (
            "Voxels where white matter is the most probable tissue (and at least "
            f"{ICBM_WM_MIN}), outside every other human layer; split into left and right at the "
            "midline; centred like the Julich-Brain label volume (same grid). It is a tissue "
            "map, not tracts. Changes made by SYNAPTICA."
        ),
    },
    "nissl": {
        "atlas": "Timm-Nissl multiplane microscopic atlas of the rat brain: coronal Nissl "
        "(thionine) series H108c, registered to Waxholm Space",
        "short": "Nissl de rata (Blixhavn et al. 2023)",
        "version": "v1, animal H108c (Wistar), 146 coronal sections",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "source": "EBRAINS, Deep Zoom pyramids and QuickNII/VisuAlign registration of H108c",
        "source_url": "https://doi.org/10.25493/T686-7BX",
        "citation": (
            "Blixhavn C. H. et al. 2023, A Timm-Nissl multiplane microscopic atlas of rat brain "
            "zincergic terminal fields and metal-containing glia, Scientific Data 10:150, "
            "https://doi.org/10.1038/s41597-023-02012-6; dataset "
            "https://doi.org/10.25493/T686-7BX"
        ),
        "derived": (
            "One reduced level of each image pyramid, resampled onto the coronal plane of the "
            "viewer (flat skull, mm from Bregma, 39 µm) with the published QuickNII and "
            "VisuAlign registration; contrast stretched (one linear map for the three "
            "channels) and the bare slide made transparent; WebP (nissl.py). Changes made by "
            "SYNAPTICA. Not "
            "combined with any atlas file."
        ),
    },
    "waxholm": {
        "atlas": "Waxholm Space atlas of the Sprague Dawley rat brain",
        "short": "Waxholm v4.01",
        "version": "v4.01",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "source": "EBRAINS Knowledge Graph, dataset version 2cf40e61-fae1-4ab3-b7de-cb8fdfa19b70",
        "source_url": "https://search.kg.ebrains.eu/instances/2cf40e61-fae1-4ab3-b7de-cb8fdfa19b70",
        "via": "BrainGlobe atlas whs_sd_rat_39um (packaging 3.0)",
        "citation": "Kleven et al. 2023, Nature Methods, https://doi.org/10.1038/s41592-023-02034-3",
        "citation_source": "BrainGlobe metadata of whs_sd_rat_39um",
        "derived": (
            "Label volume turned to flat skull (Bregma and Lambda at the same height), "
            "downsampled to 117 µm by majority vote and relabelled with compact indices per "
            "region and side; centroids and a calm colour per region. Changes made by SYNAPTICA."
        ),
    },
    "julich": {
        "atlas": "Julich-Brain Cytoarchitectonic Atlas",
        "short": "Julich-Brain v3.1",
        "version": "v3.1",
        "licence": "CC BY-NC-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "source": "Julich-Brain Atlas, cytoarchitectonic maps (v3.1), maximum probability map "
        "in MNI152 2009c nonlinear asymmetric",
        "source_url": "https://doi.org/10.25493/KNSN-XB4",
        "via": "siibra-python",
        "citation": None,  # filled from siibra: authors of the dataset + DOI
        "citation_source": "siibra (EBRAINS KG record of the dataset)",
        "derived": (
            "Left and right maximum probability maps joined into one label volume with compact "
            "indices per area and side; centroids and a calm colour per area. Changes made by "
            "SYNAPTICA. Shared under the same licence."
        ),
    },
}
