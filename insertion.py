""" in-frame and frameshift must be separated for coding sequence """
from transcripts import *
from utils import *
from record import *
from describe import *

def tnuc_coding_ins_frameshift(args, tnuc_ins, t, r):

    insseq = tnuc_ins.insseq
    tnuc_pos = tnuc_ins.beg.pos

    beg_codon_index = (tnuc_pos + 2) / 3
    beg_codon_beg = beg_codon_index*3 - 2
    if beg_codon_beg+2 > len(t.seq):
        r.append_info("truncated_refseq_at_boundary")
        err_print('truncated refseq at boundary codon end: %d, transcript length: %d' % (beg_codon_beg+3, len(t.seq)))
        raise IncompatibleTranscriptError()

    old_seq = t.seq[beg_codon_beg-1:]
    new_seq = t.seq[beg_codon_beg-1:tnuc_pos]+insseq+t.seq[tnuc_pos:]
    ret = t.extend_taa_seq(beg_codon_index, old_seq, new_seq)
    if ret:
        taa_pos, taa_ref, taa_alt, termlen = ret
        r.taa_range = '%s%d%sfs*%s' % (taa_ref, taa_pos, taa_alt, termlen)
    else:
        r.taa_range = '(=)'

def tnuc_coding_ins(args, tnuc_ins, t, r, db):

    """ assuming insertion does not affect splicing """

    insseq = tnuc_ins.insseq
    tnuc_pos = tnuc_ins.beg.pos
    
    if len(insseq) % 3 == 0:
        if tnuc_pos % 3 == 0:
            # in frame
            # insertion is after the 3rd base of a codon
            # check stop codon
            stop_codon_seen = False
            taa_insseq = ''
            for i in xrange(len(insseq)/3):
                if codon2aa(insseq[i*3:i*3+3]) == '*':
                    tnuc_coding_ins_frameshift(args, tnuc_ins, t, r)
                    stop_codon_seen = True
                    break
                taa_insseq += codon2aa(insseq[i*3:i*3+3])

            if not stop_codon_seen:
                # otherwise, a pure insertion
                c1 = t.cpos2codon((tnuc_pos+2)/3)
                c2 = t.cpos2codon((tnuc_pos+3)/3)
                if not c1 or not c2:
                    raise IncompatibleTranscriptError()
                taa_set_ins(r, t, c1.index, taa_insseq)
                r.append_info('phase=0')
        else:
            # insertion is after 1st or 2nd base of a codon
            codon_index = (tnuc_pos+2)/3
            codon = t.cpos2codon(codon_index)
            if not codon:
                raise IncompatibleTranscriptError()

            codon_beg = codon_index*3-2
            codon_end = codon_index*3
            codon_subseq1 = t.seq[codon_beg-1:tnuc_pos]
            codon_subseq2 = t.seq[tnuc_pos:codon_end]
            new_seq = codon_subseq1+insseq+codon_subseq2
            taa_insseq = ''
            for i in xrange(len(new_seq)/3):
                if codon2aa(new_seq[i*3:i*3+3]) == '*':
                    tnuc_coding_ins_frameshift(args, tnuc_ins, t, r)
                    return
                taa_insseq += codon2aa(new_seq[i*3:i*3+3])

            if not codon: raise IncompatibleTranscriptError()
            taa_ref = codon2aa(codon.seq)
            if taa_ref == taa_insseq[0]:
                # SdelinsSH becomes a pure insertion [current_codon]_[codon_after]insH
                taa_ref_after = codon2aa(t.seq[codon.index*3:codon.index*3+3])
                taa_set_ins(r, t, codon.index, taa_insseq[1:])
            elif taa_ref == taa_insseq[-1]:
                # SdelinsHS becomes a pure insertion [codon_before]_[current_codon]insH
                taa_ref_before = codon2aa(t.seq[codon.index*3-6:codon.index*3-3])
                taa_set_ins(r, t, codon.index-1, taa_insseq[:-1])
            else:
                r.taa_range = '%s%ddelins%s' % (taa_ref, codon.index, taa_insseq)
            # 0, 1,2 indicating insertion happen after 3rd, 1st or 2nd base of the codon
            r.append_info('phase=%d' % (tnuc_pos - codon_beg + 1,))

    else:                       # frameshift
        tnuc_coding_ins_frameshift(args, tnuc_ins, t, r)


def annotate_insertion_cdna(args, q, tpts, db):

    found = False
    for t in tpts:

        try:
            if q.tpt and t.name != q.tpt:
                raise IncompatibleTranscriptError("Transcript name unmatched")
            t.ensure_seq()

            r = Record()
            r.chrm = t.chrm
            r.tname = t.format()
            r.gene = t.gene.name
            r.strand = t.strand
            if t.strand == '+':
                gnuc_beg = t.tnuc2gnuc(q.pos)
                gnuc_end = gnuc_beg+1
                tnuc_beg = q.pos
                c, tnuc_end = t.gpos2codon(gnuc_end)
                gnuc_insseq = q.insseq
            else:
                gnuc_end = t.tnuc2gnuc(q.pos)
                gnuc_beg = gnuc_end-1
                tnuc_beg = q.pos
                c, tnuc_end = t.gpos2codon(gnuc_beg)
                gnuc_insseq = reverse_complement(q.insseq)

            r.pos = gnuc_beg
            gnuc_ins = gnuc_set_ins(t.chrm, gnuc_beg, gnuc_insseq, r)
            tnuc_ins = tnuc_set_ins(gnuc_ins, t, r, beg=tnuc_beg, end=tnuc_end, insseq=q.insseq)
            r.reg = describe_genic(args, t.chrm, gnuc_beg, gnuc_end, t, db)
            expt = r.set_splice()
            if not expt and r.reg.entirely_in_cds():
                tnuc_coding_ins(args, tnuc_ins, t, r, db)
        except IncompatibleTranscriptError:
            continue
        except SequenceRetrievalError:
            continue
        except UnknownChromosomeError:
            continue

        r.format(q.op)
        found = True

    if not found:
        r = Record()
        r.append_info('no_valid_transcript_found_(from_%s_candidates)' % len(tpts))
        r.format(q.op)

    return


def codon_mutation_ins(args, q, t, db):
    
    if q.tpt and t.name != q.tpt:
        raise IncompatibleTranscriptError("Transcript name unmatched")
    t.ensure_seq()

    r = Record()
    taa_set_ins(r, t, q.beg, q.insseq)
    r.reg = RegCDSAnno(t)
    r.reg.from_cindex(q.beg)
    if q.beg*3 > len(t) or q.end*3 > len(t):
        raise IncompatibleTranscriptError('codon nonexistent')

    tnuc_beg = q.beg*3-2
    tnuc_end = q.end*3
    if hasattr(q, 'beg_aa') and q.beg_aa and q.beg_aa != t.taa2aa(q.beg):
        raise IncompatibleTranscriptError('Unmatched reference amino acid')
    if hasattr(q, 'end_aa') and q.end_aa and q.end_aa != t.taa2aa(q.end):
        raise IncompatibleTranscriptError('Unmatched reference amino acid')
    gnuc_beg, gnuc_end = t.tnuc_range2gnuc_range(tnuc_beg, tnuc_end)
    r.gnuc_range = '(%dins%d)' % (gnuc_beg-1, len(q.insseq)*3)
    c, p1 = t.gpos2codon(gnuc_beg-1)
    r.tnuc_range = '(%s_%sins%d)' % (p1, tnuc_beg, len(q.insseq)*3)
    tnuc_insseq = aaseq2nuc(q.insseq)
    r.append_info('insertion_cDNA='+tnuc_insseq)
    r.append_info('insertion_gDNA=%s' % (tnuc_insseq if t.strand == '+' else reverse_complement(tnuc_insseq)))
    r.append_info('imprecise')
    r.pos = gnuc_beg-1

    return r

def annotate_insertion_protein(args, q, tpts, db):

    found = False
    for t in tpts:
        try:
            r = codon_mutation_ins(args, q, t, db)
            r.chrm = t.chrm
            r.tname = t.format()
            r.gene = t.gene.name
            r.strand = t.strand
            r.format(q.op)
            found = True
        except IncompatibleTranscriptError:
            continue
        except SequenceRetrievalError:
            continue
        except UnknownChromosomeError:
            continue

    if not found:
        r = Record()
        r.taa_range = '%s%s_%s%sins%s' % (q.beg_aa, str(q.beg), q.end_aa, str(q.end), q.insseq)
        r.append_info('no_valid_transcript_found_(from_%s_candidates)' % len(tpts))
        r.format(q.op)



def annotate_insertion_gdna(args, q, db):

    for reg in describe(args, q, db):

        r = Record()
        r.reg = reg
        r.chrm = q.tok
        r.pos = q.pos

        gnuc_ins = gnuc_set_ins(q.tok, q.pos, q.insseq, r)
        # TODO check q.insseq exists
        
        if hasattr(reg, 't'):

            t = reg.t

            r.tname = t.format()
            r.gene = t.gene.name
            r.strand = t.strand

            tnuc_ins = tnuc_set_ins(gnuc_ins, t, r)

            # TODO: check if insertion hits start codon

            # infer protein level mutation if in cds
            if reg.cds and not reg.splice: # this skips insertion that occur to sites next to donor or acceptor splicing site.
                try:
                    tnuc_coding_ins(args, tnuc_ins, t, r, db)
                except IncompatibleTranscriptError:
                    pass

                # c1 = t.cpos2codon((tnuc_ins.beg.pos+2)/3)
                # p1 = tnuc_ins.beg
                # if len(tnuc_ins.insseq) % 3 == 0:
                #     ins_gene_coding_inframe(t, r, c1, p1, tnuc_ins.insseq)
                # else:
                #     ins_gene_coding_frameshift(t, r, c1, p1, tnuc_ins.insseq)

        r.format(q.op)
        

def annotate_duplication_cdna(args, q, tpts, db):

    found = False
    for t in tpts:
        try:
            if q.tpt and t.name != q.tpt:
                raise IncompatibleTranscriptError("Transcript name unmatched")
            t.ensure_seq()

            r = Record()
            r.chrm = t.chrm
            r.tname = t.format()
            r.gene = t.gene.name
            r.strand = t.strand

            if q.beg.pos > len(t) or q.end.pos > len(t):
                raise IncompatibleTranscriptError('codon nonexistent')

            t.ensure_position_array()
            check_exon_boundary(t.np, q.beg)
            check_exon_boundary(t.np, q.end)

            _gnuc_beg = t.tnuc2gnuc(q.beg)
            _gnuc_end = t.tnuc2gnuc(q.end)
            gnuc_beg = min(_gnuc_beg, _gnuc_end)
            gnuc_end = max(_gnuc_beg, _gnuc_end)
            gnuc_dupseq = faidx.getseq(t.chrm, gnuc_beg, gnuc_end)
            tnuc_dupseq = gnuc_dupseq if t.strand == '+' else reverse_complement(gnuc_dupseq)
            if q.dupseq and tnuc_dupseq != q.dupseq:
                raise IncompatibleTranscriptError('unmatched reference')

            if t.strand == '+':
                gnuc_ins = gnuc_set_ins(t.chrm, gnuc_end, gnuc_dupseq, r)
            else:
                gnuc_ins = gnuc_set_ins(t.chrm, gnuc_beg-1, gnuc_dupseq, r)

            r.pos = gnuc_ins.beg_r
            tnuc_ins = tnuc_set_ins(gnuc_ins, t, r)
            r.reg = describe_genic(args, t.chrm, gnuc_ins.beg_r, gnuc_ins.end_r, t, db)
            expt = r.set_splice()
            if r.reg.entirely_in_cds() and not expt:
                tnuc_coding_ins(args, tnuc_ins, t, r, db)

        except IncompatibleTranscriptError:
            continue
        except SequenceRetrievalError:
            continue
        except UnknownChromosomeError:
            continue
        found = True
        r.tnuc_range = '%s_%sdup%s' % (q.beg, q.end, q.dupseq)
        r.format(q.op)

    if not found:
        r = Record()
        r.tnuc_range = '%s_%sdup%s' % (q.beg, q.end, q.dupseq)
        r.append_info('no_valid_transcript_found_(from_%s_candidates)' % len(tpts))
        r.format(q.op)


def taa_set_ins(r, t, index, taa_insseq):
    i1r, taa_insseq_r = t.taa_roll_right_ins(index, taa_insseq)
    try:
        r.taa_range = t.taa_ins_id(i1r, taa_insseq_r)
        i1l, taa_insseq_l = t.taa_roll_left_ins(index, taa_insseq)
        r.append_info('left_align_protein=p.%s' % t.taa_ins_id(i1l, taa_insseq_l))
        r.append_info('unalign_protein=p.%s' % t.taa_ins_id(index, taa_insseq))
    except IncompatibleTranscriptError:
        r.append_info("truncated_refseq_at_boundary")
